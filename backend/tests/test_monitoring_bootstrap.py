from __future__ import annotations

from threading import get_ident

import anyio
import pytest
from sqlmodel import Session

import wavemonitor_backend.db as db
import wavemonitor_backend.monitoring_bootstrap as bootstrap
from wavemonitor_backend.latest_prices import LatestPriceStore
from wavemonitor_backend.monitoring import AdapterRegistry, MonitoringScheduler, RuntimeMetricsStore
from wavemonitor_backend.settings import Settings


def test_default_poll_interval_is_two_minutes() -> None:
    assert bootstrap.DEFAULT_POLL_INTERVAL_SECONDS == 120.0


def test_poll_interval_seconds_from_env_uses_default_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(bootstrap.POLL_INTERVAL_SECONDS_ENV, raising=False)
    assert bootstrap.poll_interval_seconds_from_env() == 120.0


def test_poll_interval_seconds_from_env_parses_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(bootstrap.POLL_INTERVAL_SECONDS_ENV, "30")
    assert bootstrap.poll_interval_seconds_from_env() == 30.0


@pytest.mark.parametrize("fails", [False, True])
def test_bootstrap_session_lifetime_in_worker(
    monkeypatch: pytest.MonkeyPatch,
    fails: bool,
) -> None:
    sessions: list[Session] = []
    events: list[tuple[str, int]] = []
    failure = RuntimeError("tick failed")
    engine = db.create_database_engine("sqlite://")

    class TrackingSession(Session):
        def __init__(self, bound_engine: object) -> None:
            assert bound_engine is engine
            super().__init__(engine)
            sessions.append(self)
            events.append(("open", get_ident()))

        def close(self) -> None:
            events.append(("close", get_ident()))
            super().close()

    def run_tick(_scheduler: MonitoringScheduler, session: Session) -> None:
        assert session is sessions[-1]
        events.append(("tick", get_ident()))
        if fails:
            raise failure

    monkeypatch.setattr(db, "Session", TrackingSession)
    monkeypatch.setattr(bootstrap, "build_adapter_registry", lambda: AdapterRegistry(adapters={}))
    monkeypatch.setattr(MonitoringScheduler, "run_tick", run_tick)
    lifecycle = bootstrap.build_monitoring_lifecycle(
        engine=engine,
        settings=Settings(),
        metrics_store=RuntimeMetricsStore(),
        price_store=LatestPriceStore(),
        poll_interval_seconds=120,
    )
    assert sessions == []

    async def scenario() -> None:
        event_loop_thread = get_ident()
        for _ in range(2):
            if fails:
                with pytest.raises(RuntimeError) as caught:
                    await anyio.to_thread.run_sync(lifecycle._run_tick_in_worker)
                assert caught.value is failure
            else:
                await anyio.to_thread.run_sync(lifecycle._run_tick_in_worker)
        assert all(thread != event_loop_thread for _, thread in events)

    try:
        anyio.run(scenario)
        assert len(sessions) == 2
        assert sessions[0] is not sessions[1]
        assert [event for event, _ in events] == ["open", "tick", "close"] * 2
        for offset in (0, 3):
            assert len({thread for _, thread in events[offset : offset + 3]}) == 1
    finally:
        engine.dispose()
