from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import anyio
from fastapi.testclient import TestClient
from sqlmodel import Session

from wavemonitor_backend.app import AppRuntime, create_app
from wavemonitor_backend.db import create_database_engine, create_schema, session_scope
from wavemonitor_backend.lifecycle import MonitoringLifecycle, WakingTicker
from wavemonitor_backend.monitoring import MonitoringScheduler, RuntimeMetrics, RuntimeMetricsStore
from wavemonitor_backend.settings import Settings


class FakeAppLifecycle:
    def __init__(self) -> None:
        self.started = Event()
        self.stopped = Event()
        self.tick_requests = 0

    async def run(self) -> None:
        self.started.set()
        try:
            await anyio.sleep_forever()
        finally:
            self.stopped.set()

    def request_tick(self) -> None:
        self.tick_requests += 1


@dataclass(slots=True)
class FakeTickRunner:
    ticks: int = 0

    def run_tick(self, session: Session) -> RuntimeMetrics:
        self.ticks += 1
        return RuntimeMetrics(
            scheduler_ready=True,
            providers_ready=True,
            enabled_sources=0,
            polled_sources=0,
            observations_written=0,
            source_errors=0,
            alert_events_created=0,
            telegram_deliveries_attempted=0,
            last_tick_started_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
            last_tick_finished_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        )


class BlockingTicker:
    def __init__(self) -> None:
        self.wait_started = anyio.Event()

    async def wait(self) -> None:
        self.wait_started.set()
        await anyio.sleep_forever()


@dataclass(slots=True)
class FailingThenPassingTickRunner:
    ticks: int = 0

    def run_tick(self, session: Session) -> RuntimeMetrics:
        self.ticks += 1
        if self.ticks == 1:
            raise RuntimeError("transient scheduler failure")
        return RuntimeMetrics(
            scheduler_ready=True,
            providers_ready=True,
            enabled_sources=0,
            polled_sources=0,
            observations_written=0,
            source_errors=0,
            alert_events_created=0,
            telegram_deliveries_attempted=0,
            last_tick_started_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
            last_tick_finished_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        )


class CountingTicker:
    def __init__(self) -> None:
        self.waits = 0
        self.second_wait_started = anyio.Event()

    async def wait(self) -> None:
        self.waits += 1
        if self.waits == 2:
            self.second_wait_started.set()
        await anyio.sleep(0)


def test_app_lifespan_starts_and_stops_injected_monitoring_lifecycle(tmp_path: Path):
    # Given: the backend app receives an injected monitoring lifecycle with observable start/stop signals.
    lifecycle = FakeAppLifecycle()

    # When: TestClient enters and exits the FastAPI lifespan.
    with TestClient(
        create_app(
            AppRuntime(
                settings=Settings(),
                database_url=f"sqlite:///{tmp_path / 'lifespan.sqlite3'}",
                monitoring_lifecycle=lifecycle,
            )
        )
    ) as client:
        response = client.get("/health")
        started = lifecycle.started.wait(timeout=1)

    # Then: the lifecycle task was started during app lifespan and stopped during shutdown.
    assert response.status_code == 200
    assert started is True
    assert lifecycle.stopped.wait(timeout=1) is True


def test_monitoring_lifecycle_runs_tick_then_cleans_up_on_cancellation(tmp_path: Path):
    # Given: a lifecycle with a real SQLite session factory and a ticker that parks after the first tick.
    async def scenario() -> None:
        engine = create_database_engine(f"sqlite:///{tmp_path / 'loop.sqlite3'}")
        create_schema(engine)
        runner = FakeTickRunner()
        ticker = BlockingTicker()

        @contextmanager
        def session_factory():
            with session_scope(engine) as db_session:
                yield db_session

        lifecycle = MonitoringLifecycle(
            runner=runner,
            session_factory=session_factory,
            ticker=ticker,
        )

        # When: the background loop starts, completes one tick, then is cancelled by its task group.
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(lifecycle.run)
            await ticker.wait_started.wait()
            task_group.cancel_scope.cancel()

        # Then: the loop exits cleanly and no second tick runs after cancellation.
        assert runner.ticks == 1

    anyio.run(scenario)


def test_monitoring_lifecycle_continues_after_tick_exception(tmp_path: Path):
    # Given: the first scheduler tick raises, then the same runner can produce metrics on the next tick.
    async def scenario() -> None:
        engine = create_database_engine(f"sqlite:///{tmp_path / 'recover.sqlite3'}")
        create_schema(engine)
        runner = FailingThenPassingTickRunner()
        ticker = CountingTicker()

        @contextmanager
        def session_factory():
            with session_scope(engine) as db_session:
                yield db_session

        lifecycle = MonitoringLifecycle(
            runner=runner,
            session_factory=session_factory,
            ticker=ticker,
        )

        # When: the lifecycle observes a tick exception.
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(lifecycle.run)
            await ticker.second_wait_started.wait()
            task_group.cancel_scope.cancel()

        # Then: the lifecycle logs and continues instead of letting polling die permanently.
        assert runner.ticks == 2

    anyio.run(scenario)


def test_monitoring_lifecycle_runs_requested_tick_without_waiting_for_interval(tmp_path: Path):
    # Given: the lifecycle is parked on a long polling interval after its startup tick.
    async def scenario() -> None:
        engine = create_database_engine(f"sqlite:///{tmp_path / 'wake.sqlite3'}")
        create_schema(engine)
        runner = FakeTickRunner()
        lifecycle = MonitoringLifecycle(
            runner=runner,
            session_factory=lambda: session_scope(engine),
            ticker=WakingTicker(interval_seconds=60),
        )

        async def wait_for_ticks(expected: int) -> None:
            with anyio.fail_after(1):
                while runner.ticks < expected:
                    await anyio.sleep(0)

        # When: an external caller requests another tick while the interval wait is pending.
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(lifecycle.run)
            await wait_for_ticks(1)
            lifecycle.request_tick()
            await wait_for_ticks(2)
            task_group.cancel_scope.cancel()

        # Then: the requested tick runs immediately instead of waiting for the 60-second interval.
        assert runner.ticks == 2

    anyio.run(scenario)


def test_monitoring_scheduler_record_tick_failure_clears_readiness_flags():
    store = RuntimeMetricsStore()
    store.update(
        RuntimeMetrics(
            scheduler_ready=True,
            providers_ready=True,
            enabled_sources=2,
            polled_sources=2,
            observations_written=2,
            source_errors=0,
            alert_events_created=0,
            telegram_deliveries_attempted=0,
            last_tick_started_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
            last_tick_finished_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        )
    )

    class Clock:
        def __call__(self) -> datetime:
            return datetime(2026, 6, 30, 12, 1, tzinfo=UTC)

    scheduler = MonitoringScheduler(
        poller=object(),  # type: ignore[arg-type]
        notifier=object(),  # type: ignore[arg-type]
        clock=Clock(),
        metrics_store=store,
    )
    scheduler.record_tick_failure()

    metrics = store.metrics
    assert metrics.scheduler_ready is False
    assert metrics.providers_ready is False
    assert metrics.enabled_sources == 2
    assert metrics.last_tick_finished_at == datetime(2026, 6, 30, 12, 1, tzinfo=UTC)
