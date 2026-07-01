from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, assert_never

from sqlmodel import Session, select

from wavemonitor_backend.adapter_types import AdapterError, AdapterErrorKind, PriceAdapterResult, PriceResult
from wavemonitor_backend.api import record_telegram_delivery
from wavemonitor_backend.models import Instrument, MarketType, PriceObservation, Provider, SourceMapping
from wavemonitor_backend.notifier import MessageKind, TelegramAlert, TelegramSendResult, message_for_kind
from wavemonitor_backend.rule_persistence import evaluate_and_persist_rules, require_id


class PollingPriceAdapter(Protocol):
    def get_latest_price(self, symbol: str, market_type: MarketType) -> PriceAdapterResult: ...


class AlertNotifier(Protocol):
    def send_text(self, text: str) -> TelegramSendResult | None: ...


class Clock(Protocol):
    def __call__(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class RuntimeMetrics:
    scheduler_ready: bool
    providers_ready: bool
    enabled_sources: int
    polled_sources: int
    observations_written: int
    source_errors: int
    alert_events_created: int
    telegram_deliveries_attempted: int
    last_tick_started_at: datetime | None
    last_tick_finished_at: datetime | None


class RuntimeMetricsStore:
    def __init__(self) -> None:
        self._metrics = RuntimeMetrics(
            scheduler_ready=False,
            providers_ready=False,
            enabled_sources=0,
            polled_sources=0,
            observations_written=0,
            source_errors=0,
            alert_events_created=0,
            telegram_deliveries_attempted=0,
            last_tick_started_at=None,
            last_tick_finished_at=None,
        )

    @property
    def metrics(self) -> RuntimeMetrics:
        return self._metrics

    def update(self, metrics: RuntimeMetrics) -> None:
        self._metrics = metrics


class AdapterRegistry:
    def __init__(self, adapters: Mapping[tuple[Provider, MarketType], PollingPriceAdapter]) -> None:
        self._adapters = dict(adapters)

    def get(self, provider: Provider, market_type: MarketType) -> PollingPriceAdapter | None:
        return self._adapters.get((provider, market_type))

    def replace(self, provider: Provider, market_type: MarketType, adapter: PollingPriceAdapter) -> None:
        self._adapters[(provider, market_type)] = adapter


class SourcePoller:
    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def poll(self, source: SourceMapping) -> PriceAdapterResult:
        adapter = self._registry.get(source.provider, source.market_type)
        if adapter is None:
            return AdapterError(
                source=source.provider,
                market_type=source.market_type,
                symbol=source.symbol,
                kind=AdapterErrorKind.PROVIDER_ERROR,
                message="No price adapter is registered for source mapping",
                raw_metadata={"provider": source.provider.value, "market_type": source.market_type.value},
            )
        return adapter.get_latest_price(source.symbol, source.market_type)


class MonitoringScheduler:
    def __init__(
        self,
        poller: SourcePoller,
        notifier: AlertNotifier,
        *,
        clock: Clock | None = None,
        metrics_store: RuntimeMetricsStore | None = None,
    ) -> None:
        self._poller = poller
        self._notifier = notifier
        self._clock = clock or utc_now
        self._metrics_store = metrics_store or RuntimeMetricsStore()

    @property
    def metrics(self) -> RuntimeMetrics:
        return self._metrics_store.metrics

    def run_tick(self, session: Session) -> RuntimeMetrics:
        started_at = self._clock()
        sources = enabled_sources(session)
        counts = TickCounts(enabled_sources=len(sources))
        for instrument, source in sources:
            counts = self._poll_source(session, instrument, source, counts)
        finished_at = self._clock()
        metrics = RuntimeMetrics(
            scheduler_ready=True,
            providers_ready=counts.providers_ready,
            enabled_sources=counts.enabled_sources,
            polled_sources=counts.polled_sources,
            observations_written=counts.observations_written,
            source_errors=counts.source_errors,
            alert_events_created=counts.alert_events_created,
            telegram_deliveries_attempted=counts.telegram_deliveries_attempted,
            last_tick_started_at=started_at,
            last_tick_finished_at=finished_at,
        )
        self._metrics_store.update(metrics)
        return metrics

    def record_tick_failure(self) -> None:
        previous = self._metrics_store.metrics
        failed_at = self._clock()
        self._metrics_store.update(
            RuntimeMetrics(
                scheduler_ready=False,
                providers_ready=False,
                enabled_sources=previous.enabled_sources,
                polled_sources=previous.polled_sources,
                observations_written=previous.observations_written,
                source_errors=previous.source_errors,
                alert_events_created=previous.alert_events_created,
                telegram_deliveries_attempted=previous.telegram_deliveries_attempted,
                last_tick_started_at=previous.last_tick_started_at,
                last_tick_finished_at=failed_at,
            )
        )

    def _poll_source(
        self,
        session: Session,
        instrument: Instrument,
        source: SourceMapping,
        counts: TickCounts,
    ) -> TickCounts:
        result = self._poller.poll(source)
        match result:
            case PriceResult() as price_result:
                return self._handle_price(session, instrument, source, price_result, counts)
            case AdapterError() as error:
                record_source_error(session, source, error, self._clock())
                return counts.with_error()
            case unreachable:
                assert_never(unreachable)

    def _handle_price(
        self,
        session: Session,
        instrument: Instrument,
        source: SourceMapping,
        result: PriceResult,
        counts: TickCounts,
    ) -> TickCounts:
        record_price_observation(session, source, result)
        if not instrument.enabled:
            return counts.with_success(0, 0)
        evaluation = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=result.price,
            observed_at=result.timestamp,
        )
        deliveries = 0
        for alert in evaluation.alerts:
            message = message_for_kind(
                MessageKind.ALERT,
                TelegramAlert(
                    instrument=instrument.name,
                    source=source.identity_key,
                    rule=alert.kind,
                    price=alert.price,
                    support=alert.support,
                    resistance=alert.resistance,
                ),
            )
            send_result = self._notifier.send_text(message)
            if send_result is not None:
                record_telegram_delivery(
                    session,
                    message_kind=MessageKind.ALERT.value,
                    message_text=message,
                    result=send_result,
                )
                deliveries += 1
        return counts.with_success(len(evaluation.alerts), deliveries)


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class TickCounts:
    enabled_sources: int
    polled_sources: int = 0
    observations_written: int = 0
    source_errors: int = 0
    source_successes: int = 0
    alert_events_created: int = 0
    telegram_deliveries_attempted: int = 0

    @property
    def providers_ready(self) -> bool:
        if self.enabled_sources == 0:
            return True
        if self.polled_sources != self.enabled_sources:
            return False
        return self.source_errors == 0

    def with_success(self, alerts: int, deliveries: int) -> TickCounts:
        return TickCounts(
            enabled_sources=self.enabled_sources,
            polled_sources=self.polled_sources + 1,
            observations_written=self.observations_written + 1,
            source_errors=self.source_errors,
            source_successes=self.source_successes + 1,
            alert_events_created=self.alert_events_created + alerts,
            telegram_deliveries_attempted=self.telegram_deliveries_attempted + deliveries,
        )

    def with_error(self) -> TickCounts:
        return TickCounts(
            enabled_sources=self.enabled_sources,
            polled_sources=self.polled_sources + 1,
            observations_written=self.observations_written,
            source_errors=self.source_errors + 1,
            source_successes=self.source_successes,
            alert_events_created=self.alert_events_created,
            telegram_deliveries_attempted=self.telegram_deliveries_attempted,
        )


def enabled_sources(session: Session) -> list[tuple[Instrument, SourceMapping]]:
    instruments = session.exec(select(Instrument).order_by(Instrument.id)).all()
    pairs: list[tuple[Instrument, SourceMapping]] = []
    for instrument in instruments:
        instrument_id = require_id(instrument.id)
        sources = session.exec(
            select(SourceMapping)
            .where(SourceMapping.instrument_id == instrument_id, SourceMapping.enabled)
            .order_by(SourceMapping.id)
        ).all()
        pairs.extend((instrument, source) for source in sources)
    return pairs


def record_price_observation(session: Session, source: SourceMapping, result: PriceResult) -> None:
    path = result.raw_metadata.get("path")
    session.add(
        PriceObservation(
            source_mapping_id=require_id(source.id),
            price=result.price,
            observed_at=result.timestamp,
            raw_path=path if isinstance(path, str) else None,
        )
    )


def record_source_error(session: Session, source: SourceMapping, error: AdapterError, observed_at: datetime) -> None:
    session.add(
        PriceObservation(
            source_mapping_id=require_id(source.id),
            price=None,
            observed_at=observed_at,
            error=f"{error.kind.value}: {error.message}",
        )
    )
    session.commit()
