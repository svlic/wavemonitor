from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from threading import get_ident
from typing import Protocol, runtime_checkable

import anyio
from anyio import from_thread
from anyio.lowlevel import EventLoopToken, current_token
from sqlmodel import Session

from wavemonitor_backend.monitoring import RuntimeMetrics

LOGGER = logging.getLogger("wavemonitor_backend.lifecycle")


class TickRunner(Protocol):
    def run_tick(self, session: Session) -> RuntimeMetrics: ...


class LifecycleTicker(Protocol):
    async def wait(self) -> None: ...


@runtime_checkable
class ImmediateTickRequester(Protocol):
    def request_tick(self) -> None: ...


SessionFactory = Callable[[], AbstractContextManager[Session]]


class WakingTicker:
    def __init__(self, interval_seconds: float) -> None:
        self.interval_seconds = interval_seconds
        self._wake_event: anyio.Event | None = None
        self._token: EventLoopToken | None = None
        self._event_loop_thread_id: int | None = None
        self._wake_requested = False

    async def wait(self) -> None:
        if self._wake_requested:
            self._wake_requested = False
            return
        wake_event = anyio.Event()
        self._wake_event = wake_event
        self._token = current_token()
        self._event_loop_thread_id = get_ident()
        with anyio.move_on_after(self.interval_seconds):
            await wake_event.wait()
        self._wake_event = None
        self._token = None
        self._event_loop_thread_id = None
        self._wake_requested = False

    def request_tick(self) -> None:
        wake_event = self._wake_event
        token = self._token
        if wake_event is None or token is None:
            self._wake_requested = True
            return
        if self._event_loop_thread_id == get_ident():
            wake_event.set()
            return
        from_thread.run_sync(wake_event.set, token=token)


class MonitoringLifecycle:
    def __init__(
        self,
        runner: TickRunner,
        session_factory: SessionFactory,
        ticker: LifecycleTicker,
    ) -> None:
        self._runner = runner
        self._session_factory = session_factory
        self._ticker = ticker

    async def run(self) -> None:
        while True:
            try:
                # Whole sync tick (urlopen/sleep/SQLite) off the event loop.
                # Session is created inside the worker thread for SQLite safety.
                await anyio.to_thread.run_sync(self._run_tick_in_worker)
            except Exception:
                LOGGER.exception("monitoring scheduler tick failed; continuing after interval")
                record_failure = getattr(self._runner, "record_tick_failure", None)
                if callable(record_failure):
                    record_failure()
            await self._ticker.wait()

    def _run_tick_in_worker(self) -> None:
        with self._session_factory() as session:
            self._runner.run_tick(session)

    def request_tick(self) -> None:
        if isinstance(self._ticker, ImmediateTickRequester):
            self._ticker.request_tick()
