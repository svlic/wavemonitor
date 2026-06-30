from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from wavemonitor_backend.app import AppRuntime, create_app
from wavemonitor_backend.monitoring import RuntimeMetrics, RuntimeMetricsStore
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
