from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final

import pytest
from sqlmodel import Session, select

from wavemonitor_backend.adapters import (
    AdapterError,
    AdapterErrorKind,
    PriceAdapterResult,
    PriceResult,
)
from wavemonitor_backend.db import create_database_engine, create_schema, session_scope
from wavemonitor_backend.models import (
    AlertEvent,
    AlertKind,
    DeliveryStatus,
    Instrument,
    LastRuleState,
    MarketType,
    Provider,
    SourceMapping,
    TelegramDelivery,
)
from wavemonitor_backend.monitoring import (
    AdapterRegistry,
    MonitoringScheduler,
    RuntimeMetrics,
)
from wavemonitor_backend.notifier import (
    TelegramHttpFailure,
    TelegramSendResult,
    TelegramSendSuccess,
)

BASE_TIME: Final[datetime] = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


@dataclass(slots=True)
class FakePriceAdapter:
    result: PriceAdapterResult

    def get_latest_price(self, symbol: str, market_type: MarketType) -> PriceAdapterResult:
        return self.result


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def set(self, current: datetime) -> None:
        self.current = current


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_text(self, text: str) -> TelegramSendSuccess:
        self.messages.append(text)
        return TelegramSendSuccess(message_id=f"fake-{len(self.messages)}")


class FailingThenSucceedingNotifier:
    def __init__(self, failures_before_success: int) -> None:
        self.messages: list[str] = []
        self._remaining_failures = failures_before_success

    def send_text(self, text: str) -> TelegramSendResult:
        self.messages.append(text)
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            return TelegramHttpFailure(status_code=500, description="temporary outage")
        return TelegramSendSuccess(message_id=f"fake-{len(self.messages)}")


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'scheduler.sqlite3'}")
    create_schema(engine)
    with session_scope(engine) as db_session:
        yield db_session


def seed_instrument(session: Session) -> tuple[Instrument, list[SourceMapping]]:
    instrument = Instrument(
        name="Bitcoin",
        supports=[Decimal("98")],
        resistances=[Decimal("130")],
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        rule_cycle_started_at=BASE_TIME,
    )
    session.add(instrument)
    session.commit()
    session.refresh(instrument)
    sources = [
        SourceMapping(
            instrument_id=instrument.id,
            provider=Provider.YFINANCE,
            market_type=MarketType.EQUITY,
            symbol="BTC",
        ),
        SourceMapping(
            instrument_id=instrument.id,
            provider=Provider.BINANCE,
            market_type=MarketType.USD_M_FUTURES,
            symbol="BTCUSDT",
        ),
        SourceMapping(
            instrument_id=instrument.id,
            provider=Provider.HYPERLIQUID,
            market_type=MarketType.PERPETUAL,
            symbol="BTC",
        ),
    ]
    for source in sources:
        session.add(source)
    session.commit()
    for source in sources:
        session.refresh(source)
    return instrument, sources


def price(
    provider: Provider, market_type: MarketType, symbol: str, value: str, observed_at: datetime
) -> PriceResult:
    return PriceResult(
        source=provider,
        market_type=market_type,
        symbol=symbol,
        price=Decimal(value),
        timestamp=observed_at,
        raw_metadata={"path": "fake.price", "raw_price": value},
    )


def test_poll_tick_keeps_prices_in_memory_and_persists_alerts_deliveries_and_states(
    session: Session,
):
    # Given: one enabled instrument has three enabled source mappings and fake prices near support.
    instrument, sources = seed_instrument(session)
    instrument.risk_reward_threshold = Decimal("10")
    session.add(instrument)
    session.commit()
    clock = FakeClock(BASE_TIME)
    notifier = FakeNotifier()
    registry = AdapterRegistry(
        adapters={
            (Provider.YFINANCE, MarketType.EQUITY): FakePriceAdapter(
                price(Provider.YFINANCE, MarketType.EQUITY, "BTC", "100", BASE_TIME)
            ),
            (Provider.BINANCE, MarketType.USD_M_FUTURES): FakePriceAdapter(
                price(Provider.BINANCE, MarketType.USD_M_FUTURES, "BTCUSDT", "100", BASE_TIME)
            ),
            (Provider.HYPERLIQUID, MarketType.PERPETUAL): FakePriceAdapter(
                price(Provider.HYPERLIQUID, MarketType.PERPETUAL, "BTC", "100", BASE_TIME)
            ),
        }
    )
    scheduler = MonitoringScheduler(registry, notifier, clock=clock)

    # When: the scheduler runs one deterministic polling tick.
    metrics = scheduler.run_tick(session)

    # Then: prices stay in memory while alerts, deliveries, and rule states are persisted.
    price_statuses = [scheduler.price_store.get(source.id) for source in sources]
    alerts = session.exec(select(AlertEvent).order_by(AlertEvent.source_mapping_id)).all()
    deliveries = session.exec(select(TelegramDelivery).order_by(TelegramDelivery.id)).all()
    states = session.exec(select(LastRuleState).order_by(LastRuleState.source_mapping_id)).all()
    assert [status.latest_success.price for status in price_statuses if status is not None] == [
        Decimal("100")
    ] * 3
    assert [status.last_error for status in price_statuses if status is not None] == [None] * 3
    assert len(alerts) == 6
    assert {alert.instrument_id for alert in alerts} == {instrument.id}
    assert {alert.source_mapping_id for alert in alerts} == {source.id for source in sources}
    assert [delivery.status for delivery in deliveries] == [DeliveryStatus.SENT] * 6
    assert len(notifier.messages) == 6
    assert metrics == RuntimeMetrics(
        scheduler_ready=True,
        providers_ready=True,
        enabled_sources=3,
        polled_sources=3,
        observations_written=3,
        source_errors=0,
        alert_events_created=6,
        telegram_deliveries_attempted=6,
        last_tick_started_at=BASE_TIME,
        last_tick_finished_at=BASE_TIME,
    )
    assert [state.near_support_active for state in states] == [True, True, True]
    assert [state.risk_reward_active for state in states] == [True, True, True]


def test_poll_tick_rearms_source_rule_after_condition_resets(session: Session):
    # Given: a first tick already emitted near-support alerts for all three sources.
    seed_instrument(session)
    clock = FakeClock(BASE_TIME)
    notifier = FakeNotifier()
    binance_adapter = FakePriceAdapter(
        price(Provider.BINANCE, MarketType.USD_M_FUTURES, "BTCUSDT", "100", BASE_TIME)
    )
    registry = AdapterRegistry(
        adapters={
            (Provider.YFINANCE, MarketType.EQUITY): FakePriceAdapter(
                price(Provider.YFINANCE, MarketType.EQUITY, "BTC", "100", BASE_TIME)
            ),
            (Provider.BINANCE, MarketType.USD_M_FUTURES): binance_adapter,
            (Provider.HYPERLIQUID, MarketType.PERPETUAL): FakePriceAdapter(
                price(Provider.HYPERLIQUID, MarketType.PERPETUAL, "BTC", "100", BASE_TIME)
            ),
        }
    )
    scheduler = MonitoringScheduler(registry, notifier, clock=clock)
    first = scheduler.run_tick(session)

    # When: price repeats, resets away from support, then returns near support.
    clock.set(BASE_TIME + timedelta(minutes=1))
    second = scheduler.run_tick(session)
    binance_adapter.result = price(
        Provider.BINANCE, MarketType.USD_M_FUTURES, "BTCUSDT", "120", clock.current
    )
    clock.set(BASE_TIME + timedelta(minutes=2))
    reset = scheduler.run_tick(session)
    binance_adapter.result = price(
        Provider.BINANCE, MarketType.USD_M_FUTURES, "BTCUSDT", "100", clock.current
    )
    clock.set(BASE_TIME + timedelta(minutes=3))
    retrigger = scheduler.run_tick(session)

    # Then: each source/rule tuple emits on the first tick and re-arms after a reset.
    alerts = session.exec(
        select(AlertEvent).order_by(AlertEvent.triggered_at, AlertEvent.source_mapping_id)
    ).all()
    assert first.alert_events_created == 3
    assert second.alert_events_created == 0
    assert reset.alert_events_created == 0
    assert retrigger.alert_events_created == 1
    assert len(alerts) == 4
    assert [delivery.status for delivery in session.exec(select(TelegramDelivery)).all()] == [
        DeliveryStatus.SENT,
        DeliveryStatus.SENT,
        DeliveryStatus.SENT,
        DeliveryStatus.SENT,
    ]
    assert len(notifier.messages) == 4


def test_poll_tick_records_one_source_error_and_continues_other_sources(session: Session):
    # Given: one source adapter fails while two other fake adapters return prices.
    _instrument, sources = seed_instrument(session)
    clock = FakeClock(BASE_TIME)
    notifier = FakeNotifier()
    registry = AdapterRegistry(
        adapters={
            (Provider.YFINANCE, MarketType.EQUITY): FakePriceAdapter(
                AdapterError(
                    source=Provider.YFINANCE,
                    market_type=MarketType.EQUITY,
                    symbol="BTC",
                    kind=AdapterErrorKind.PROVIDER_ERROR,
                    message="provider down; " * 50,
                    raw_metadata={"provider": "fake"},
                )
            ),
            (Provider.BINANCE, MarketType.USD_M_FUTURES): FakePriceAdapter(
                price(Provider.BINANCE, MarketType.USD_M_FUTURES, "BTCUSDT", "100", BASE_TIME)
            ),
            (Provider.HYPERLIQUID, MarketType.PERPETUAL): FakePriceAdapter(
                price(Provider.HYPERLIQUID, MarketType.PERPETUAL, "BTC", "100", BASE_TIME)
            ),
        }
    )
    scheduler = MonitoringScheduler(registry, notifier, clock=clock)

    # When: the scheduler polls all enabled mappings.
    metrics = scheduler.run_tick(session)

    # Then: the failing source records an in-memory error and other sources still alert/deliver.
    statuses = [scheduler.price_store.get(source.id) for source in sources]
    alerts = session.exec(select(AlertEvent).order_by(AlertEvent.source_mapping_id)).all()
    assert [status.last_error for status in statuses if status is not None] == [
        f"provider_error: {'provider down; ' * 50}"[:500],
        None,
        None,
    ]
    assert [
        status.latest_success.price if status is not None and status.latest_success else None
        for status in statuses
    ] == [
        None,
        Decimal("100"),
        Decimal("100"),
    ]
    assert len(alerts) == 2
    assert metrics.providers_ready is False
    assert metrics.source_errors == 1
    assert metrics.observations_written == 2
    assert metrics.telegram_deliveries_attempted == 2
    assert len(notifier.messages) == 2


def test_poll_tick_does_not_poll_disabled_instrument(session: Session):
    instrument, _sources = seed_instrument(session)
    instrument.enabled = False
    session.add(instrument)
    session.commit()
    clock = FakeClock(BASE_TIME)
    notifier = FakeNotifier()
    registry = AdapterRegistry(
        adapters={
            (Provider.YFINANCE, MarketType.EQUITY): FakePriceAdapter(
                price(Provider.YFINANCE, MarketType.EQUITY, "BTC", "100", BASE_TIME)
            ),
            (Provider.BINANCE, MarketType.USD_M_FUTURES): FakePriceAdapter(
                price(Provider.BINANCE, MarketType.USD_M_FUTURES, "BTCUSDT", "100", BASE_TIME)
            ),
            (Provider.HYPERLIQUID, MarketType.PERPETUAL): FakePriceAdapter(
                price(Provider.HYPERLIQUID, MarketType.PERPETUAL, "BTC", "100", BASE_TIME)
            ),
        }
    )
    scheduler = MonitoringScheduler(registry, notifier, clock=clock)

    metrics = scheduler.run_tick(session)

    assert session.exec(select(AlertEvent)).all() == []
    assert session.exec(select(LastRuleState)).all() == []
    assert notifier.messages == []
    assert metrics.enabled_sources == 0
    assert metrics.polled_sources == 0
    assert metrics.observations_written == 0
    assert metrics.alert_events_created == 0
    assert metrics.telegram_deliveries_attempted == 0


def test_poll_tick_keeps_last_success_in_memory_after_newer_error(session: Session):
    # Given: all sources first return successful prices.
    _instrument, sources = seed_instrument(session)
    clock = FakeClock(BASE_TIME)
    yfinance_adapter = FakePriceAdapter(
        price(Provider.YFINANCE, MarketType.EQUITY, "BTC", "120", BASE_TIME)
    )
    registry = AdapterRegistry(
        adapters={
            (Provider.YFINANCE, MarketType.EQUITY): yfinance_adapter,
            (Provider.BINANCE, MarketType.USD_M_FUTURES): FakePriceAdapter(
                price(Provider.BINANCE, MarketType.USD_M_FUTURES, "BTCUSDT", "120", BASE_TIME)
            ),
            (Provider.HYPERLIQUID, MarketType.PERPETUAL): FakePriceAdapter(
                price(Provider.HYPERLIQUID, MarketType.PERPETUAL, "BTC", "120", BASE_TIME)
            ),
        }
    )
    scheduler = MonitoringScheduler(registry, FakeNotifier(), clock=clock)
    scheduler.run_tick(session)

    # When: one source fails on the next tick.
    clock.set(BASE_TIME + timedelta(minutes=1))
    yfinance_adapter.result = AdapterError(
        source=Provider.YFINANCE,
        market_type=MarketType.EQUITY,
        symbol="BTC",
        kind=AdapterErrorKind.PROVIDER_ERROR,
        message="provider down",
        raw_metadata={},
    )
    scheduler.run_tick(session)

    # Then: the successful price remains available beside the latest error without DB rows.
    status = scheduler.price_store.get(sources[0].id)
    assert status is not None
    assert status.latest_success is not None
    assert status.latest_success.price == Decimal("120")
    assert status.latest_success.observed_at == BASE_TIME
    assert status.last_attempt_at == BASE_TIME + timedelta(minutes=1)
    assert status.last_error == "provider_error: provider down"


def test_edit_during_poll_uses_new_rule_cycle(session: Session):
    # Given: a PUT-equivalent edit commits while one source returns an old-cycle quote.
    instrument, sources = seed_instrument(session)
    for source in sources[1:]:
        source.enabled = False
        session.add(source)
    session.commit()
    instrument_id = instrument.id
    assert instrument_id is not None
    new_cycle = BASE_TIME + timedelta(minutes=1)
    engine = session.get_bind()

    @dataclass(frozen=True, slots=True)
    class EditingAdapter:
        def get_latest_price(self, symbol: str, market_type: MarketType) -> PriceAdapterResult:
            with Session(engine) as edit_session:
                current = edit_session.get(Instrument, instrument_id)
                assert current is not None
                current.updated_at = new_cycle
                current.rule_cycle_started_at = new_cycle
                edit_session.add(current)
                edit_session.commit()
            return price(Provider.YFINANCE, market_type, symbol, "90", BASE_TIME)

    notifier = FakeNotifier()
    registry = AdapterRegistry(adapters={(Provider.YFINANCE, MarketType.EQUITY): EditingAdapter()})
    scheduler = MonitoringScheduler(registry, notifier, clock=FakeClock(new_cycle))

    # When: the scheduler completes the poll that straddled the edit.
    metrics = scheduler.run_tick(session)

    # Then: the price remains in memory, but old-cycle rule side effects are suppressed.
    price_status = scheduler.price_store.get(sources[0].id)
    assert price_status is not None
    assert price_status.latest_success is not None
    assert price_status.latest_success.price == Decimal("90")
    assert session.exec(select(AlertEvent)).all() == []
    assert session.exec(select(LastRuleState)).all() == []
    assert metrics.observations_written == 1
    assert metrics.alert_events_created == 0
    assert notifier.messages == []


def test_failed_telegram_delivery_does_not_repeat_alert_next_tick(session: Session):
    # Given: one source near support and a notifier that fails once then succeeds.
    seed_instrument(session)
    clock = FakeClock(BASE_TIME)
    notifier = FailingThenSucceedingNotifier(failures_before_success=3)
    registry = AdapterRegistry(
        adapters={
            (Provider.YFINANCE, MarketType.EQUITY): FakePriceAdapter(
                price(Provider.YFINANCE, MarketType.EQUITY, "BTC", "100", BASE_TIME)
            ),
            (Provider.BINANCE, MarketType.USD_M_FUTURES): FakePriceAdapter(
                price(Provider.BINANCE, MarketType.USD_M_FUTURES, "BTCUSDT", "100", BASE_TIME)
            ),
            (Provider.HYPERLIQUID, MarketType.PERPETUAL): FakePriceAdapter(
                price(Provider.HYPERLIQUID, MarketType.PERPETUAL, "BTC", "100", BASE_TIME)
            ),
        }
    )
    scheduler = MonitoringScheduler(registry, notifier, clock=clock)

    # When: the first tick fails delivery; the second tick still sees the active condition.
    first = scheduler.run_tick(session)
    clock.set(BASE_TIME + timedelta(minutes=1))
    second = scheduler.run_tick(session)

    # Then: a failed attempt still consumes the tuple and the next tick does not resend it.
    alerts = session.exec(select(AlertEvent).order_by(AlertEvent.triggered_at)).all()
    deliveries = session.exec(select(TelegramDelivery).order_by(TelegramDelivery.id)).all()
    states = session.exec(select(LastRuleState)).all()
    assert first.alert_events_created == 3
    assert second.alert_events_created == 0
    assert len(alerts) == 3
    assert all(alert.alert_kind == AlertKind.NEAR_SUPPORT for alert in alerts)
    assert [delivery.status for delivery in deliveries] == [DeliveryStatus.FAILED] * 3
    assert all(state.near_support_last_alert_at is not None for state in states)
    assert len(notifier.messages) == 3
