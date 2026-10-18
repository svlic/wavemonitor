from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from wavemonitor_backend.adapters import PriceResult
from wavemonitor_backend.app import AppRuntime, create_app
from wavemonitor_backend.db import create_database_engine, create_schema, session_scope
from wavemonitor_backend.latest_prices import LatestPriceStore
from wavemonitor_backend.lifecycle import MonitoringLifecycle, WakingTicker
from wavemonitor_backend.models import Instrument, MarketType, Provider, SourceMapping
from wavemonitor_backend.monitoring import (
    AdapterRegistry,
    MonitoringScheduler,
    RuntimeMetrics,
    RuntimeMetricsStore,
)
from wavemonitor_backend.notifier import TelegramNotifier
from wavemonitor_backend.settings import Settings


def test_runtime_endpoint_reports_injected_scheduler_metrics(tmp_path: Path):
    # Given: the backend app receives a metrics store updated by the monitoring runtime.
    metrics_store = RuntimeMetricsStore()
    metrics_store.update(
        RuntimeMetrics(
            scheduler_ready=True,
            providers_ready=False,
            enabled_sources=3,
            polled_sources=3,
            observations_written=2,
            source_errors=1,
            alert_events_created=2,
            telegram_deliveries_attempted=2,
            last_tick_started_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
            last_tick_finished_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        )
    )

    # When: the runtime endpoint is requested offline.
    with TestClient(
        create_app(
            AppRuntime(
                settings=Settings(),
                database_url=f"sqlite:///{tmp_path / 'runtime.sqlite3'}",
                metrics_store=metrics_store,
            )
        )
    ) as client:
        response = client.get("/api/runtime")

    # Then: deterministic scheduler/provider/status counters are visible to the backend API.
    assert response.status_code == 200
    assert response.json() == {
        "scheduler_ready": True,
        "providers_ready": False,
        "telegram_ready": False,
        "enabled_sources": 3,
        "polled_sources": 3,
        "observations_written": 2,
        "source_errors": 1,
        "alert_events_created": 2,
        "telegram_deliveries_attempted": 2,
        "last_tick_started_at": "2026-06-30T12:00:00Z",
        "last_tick_finished_at": "2026-06-30T12:00:00Z",
    }


def test_manual_refresh_publishes_new_prices_before_responding(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'refresh.sqlite3'}"
    engine = create_database_engine(database_url)
    create_schema(engine)
    with session_scope(engine) as session:
        instrument = Instrument(
            name="Test",
            supports=[Decimal("10")],
            near_support_threshold=Decimal("0.01"),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(instrument)
        session.commit()
        session.add(
            SourceMapping(
                instrument_id=instrument.id,
                provider=Provider.YFINANCE,
                market_type=MarketType.EQUITY,
                symbol="TEST",
            )
        )
        session.commit()

    class Adapter:
        value = Decimal("100")

        def get_latest_price(self, symbol: str, market_type: MarketType) -> PriceResult:
            return PriceResult(
                Provider.YFINANCE,
                market_type,
                symbol,
                self.value,
                datetime.now(UTC),
                {},
            )

    adapter = Adapter()
    prices = LatestPriceStore()
    metrics = RuntimeMetricsStore()
    settings = Settings()
    scheduler = MonitoringScheduler(
        AdapterRegistry({(Provider.YFINANCE, MarketType.EQUITY): adapter}),
        TelegramNotifier(settings),
        price_store=prices,
        metrics_store=metrics,
    )
    lifecycle = MonitoringLifecycle(scheduler, lambda: session_scope(engine), WakingTicker(3600))
    with TestClient(
        create_app(
            AppRuntime(
                settings=settings,
                database_url=database_url,
                price_store=prices,
                metrics_store=metrics,
                monitoring_lifecycle=lifecycle,
            )
        )
    ) as client:
        assert client.post("/api/prices/refresh").status_code == 204
        assert Decimal(client.get("/api/prices/latest").json()[0]["last_price"]) == Decimal("100")
        adapter.value = Decimal("137")
        # A read alone must not poll the adapter.
        assert Decimal(client.get("/api/prices/latest").json()[0]["last_price"]) == Decimal("100")
        assert client.post("/api/prices/refresh").status_code == 204
        assert Decimal(client.get("/api/prices/latest").json()[0]["last_price"]) == Decimal("137")
