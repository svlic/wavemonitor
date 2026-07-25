from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final

import pytest
from sqlmodel import Session, select

from wavemonitor_backend.adapter_types import (
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
    PriceObservation,
    Provider,
    SourceMapping,
    TelegramDelivery,
)
from wavemonitor_backend.monitoring import (
    OBSERVATION_RETENTION,
    AdapterRegistry,
    MonitoringScheduler,
    RuntimeMetrics,
    SourcePoller,
)
from wavemonitor_backend.notifier import (
    TelegramHttpFailure,
    TelegramSendResult,
    TelegramSendSuccess,
)

BASE_TIME: Final[datetime] = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
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
        support=Decimal("98"),
        resistance=Decimal("130"),
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


def test_poll_tick_writes_observations_alerts_deliveries_and_metrics(session: Session):
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
    scheduler = MonitoringScheduler(SourcePoller(registry), notifier, clock=clock)

    # When: the scheduler runs one deterministic polling tick.
    metrics = scheduler.run_tick(session)

    # Then: every new alert event is persisted and delivered once per source/rule.
    observations = session.exec(
        select(PriceObservation).order_by(PriceObservation.source_mapping_id)
    ).all()
    alerts = session.exec(select(AlertEvent).order_by(AlertEvent.source_mapping_id)).all()
    deliveries = session.exec(select(TelegramDelivery).order_by(TelegramDelivery.id)).all()
    states = session.exec(select(LastRuleState).order_by(LastRuleState.source_mapping_id)).all()
    assert [observation.price for observation in observations] == [Decimal("100.0000000000")] * 3
    assert [observation.raw_path for observation in observations] == ["fake.price"] * 3
    assert [observation.error for observation in observations] == [None, None, None]
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


def test_poll_tick_sends_each_source_rule_only_once_after_condition_resets(session: Session):
    # Given: a first tick already emitted near-support alerts for all three sources.
    seed_instrument(session)
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
    scheduler = MonitoringScheduler(SourcePoller(registry), notifier, clock=clock)
    first = scheduler.run_tick(session)

    # When: price repeats, resets away from support, then returns near support.
    clock.set(BASE_TIME + timedelta(minutes=1))
    second = scheduler.run_tick(session)
    registry.replace(
        Provider.BINANCE,
        MarketType.USD_M_FUTURES,
        FakePriceAdapter(
            price(Provider.BINANCE, MarketType.USD_M_FUTURES, "BTCUSDT", "120", clock.current)
        ),
    )
    clock.set(BASE_TIME + timedelta(minutes=2))
    reset = scheduler.run_tick(session)
    registry.replace(
        Provider.BINANCE,
        MarketType.USD_M_FUTURES,
        FakePriceAdapter(
            price(Provider.BINANCE, MarketType.USD_M_FUTURES, "BTCUSDT", "100", clock.current)
        ),
    )
    clock.set(BASE_TIME + timedelta(minutes=3))
    retrigger = scheduler.run_tick(session)

    # Then: each source/rule tuple sends only once, even after the condition resets.
    alerts = session.exec(
        select(AlertEvent).order_by(AlertEvent.triggered_at, AlertEvent.source_mapping_id)
    ).all()
    observations = session.exec(select(PriceObservation)).all()
    assert first.alert_events_created == 3
    assert second.alert_events_created == 0
    assert reset.alert_events_created == 0
    assert retrigger.alert_events_created == 0
    assert len(alerts) == 3
    assert len(observations) == 12
    assert [delivery.status for delivery in session.exec(select(TelegramDelivery)).all()] == [
        DeliveryStatus.SENT,
        DeliveryStatus.SENT,
        DeliveryStatus.SENT,
    ]
    assert len(notifier.messages) == 3


def test_poll_tick_records_one_source_error_and_continues_other_sources(session: Session):
    # Given: one source adapter fails while two other fake adapters return prices.
    seed_instrument(session)
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
                    message="provider down",
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
    scheduler = MonitoringScheduler(SourcePoller(registry), notifier, clock=clock)

    # When: the scheduler polls all enabled mappings.
    metrics = scheduler.run_tick(session)

    # Then: the failing source records an observation error and other sources still alert/deliver.
    observations = session.exec(
        select(PriceObservation).order_by(PriceObservation.source_mapping_id)
    ).all()
    alerts = session.exec(select(AlertEvent).order_by(AlertEvent.source_mapping_id)).all()
    assert [observation.error for observation in observations] == [
        "provider_error: provider down",
        None,
        None,
    ]
    assert [observation.price for observation in observations] == [
        None,
        Decimal("100.0000000000"),
        Decimal("100.0000000000"),
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
    scheduler = MonitoringScheduler(SourcePoller(registry), notifier, clock=clock)

    metrics = scheduler.run_tick(session)

    assert session.exec(select(PriceObservation)).all() == []
    assert session.exec(select(AlertEvent)).all() == []
    assert session.exec(select(LastRuleState)).all() == []
    assert notifier.messages == []
    assert metrics.enabled_sources == 0
    assert metrics.polled_sources == 0
    assert metrics.observations_written == 0
    assert metrics.alert_events_created == 0
    assert metrics.telegram_deliveries_attempted == 0


def test_poll_tick_prunes_observations_older_than_retention(session: Session):
    # Given: one stale observation older than retention and one recent observation.
    instrument, sources = seed_instrument(session)
    source = sources[0]
    stale_at = BASE_TIME - OBSERVATION_RETENTION - timedelta(hours=1)
    recent_at = BASE_TIME - timedelta(hours=1)
    session.add(
        PriceObservation(
            source_mapping_id=source.id,
            price=Decimal("90"),
            observed_at=stale_at,
        )
    )
    session.add(
        PriceObservation(
            source_mapping_id=source.id,
            price=Decimal("95"),
            observed_at=recent_at,
        )
    )
    session.commit()
    clock = FakeClock(BASE_TIME)
    registry = AdapterRegistry(
        adapters={
            (Provider.YFINANCE, MarketType.EQUITY): FakePriceAdapter(
                price(Provider.YFINANCE, MarketType.EQUITY, "BTC", "120", BASE_TIME)
            ),
            (Provider.BINANCE, MarketType.USD_M_FUTURES): FakePriceAdapter(
                price(Provider.BINANCE, MarketType.USD_M_FUTURES, "BTCUSDT", "120", BASE_TIME)
            ),
            (Provider.HYPERLIQUID, MarketType.PERPETUAL): FakePriceAdapter(
                price(Provider.HYPERLIQUID, MarketType.PERPETUAL, "BTC", "120", BASE_TIME)
            ),
        }
    )
    scheduler = MonitoringScheduler(SourcePoller(registry), FakeNotifier(), clock=clock)

    # When: a tick runs with the retention window relative to the clock.
    scheduler.run_tick(session)

    # Then: only the stale row is removed; recent and new observations remain.
    observed_ats = sorted(
        observation.observed_at for observation in session.exec(select(PriceObservation)).all()
    )
    assert stale_at.replace(tzinfo=None) not in observed_ats
    assert recent_at.replace(tzinfo=None) in observed_ats
    assert BASE_TIME.replace(tzinfo=None) in observed_ats
    assert instrument.id is not None


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
        def get_latest_price(
            self, symbol: str, market_type: MarketType
        ) -> PriceAdapterResult:
            with Session(engine) as edit_session:
                current = edit_session.get(Instrument, instrument_id)
                assert current is not None
                current.updated_at = new_cycle
                current.rule_cycle_started_at = new_cycle
                edit_session.add(current)
                edit_session.commit()
            return price(Provider.YFINANCE, market_type, symbol, "90", BASE_TIME)

    notifier = FakeNotifier()
    registry = AdapterRegistry(
        adapters={(Provider.YFINANCE, MarketType.EQUITY): EditingAdapter()}
    )
    scheduler = MonitoringScheduler(SourcePoller(registry), notifier, clock=FakeClock(new_cycle))

    # When: the scheduler completes the poll that straddled the edit.
    metrics = scheduler.run_tick(session)

    # Then: the price observation remains, but old-cycle rule side effects are suppressed.
    assert len(session.exec(select(PriceObservation)).all()) == 1
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
    scheduler = MonitoringScheduler(SourcePoller(registry), notifier, clock=clock)

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
