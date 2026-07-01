from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

import anyio
from sqlmodel import Session

from wavemonitor_backend.monitoring import RuntimeMetrics

LOGGER = logging.getLogger("wavemonitor_backend.lifecycle")


class TickRunner(Protocol):
    def run_tick(self, session: Session) -> RuntimeMetrics: ...


class LifecycleTicker(Protocol):
    async def wait(self) -> None: ...


SessionFactory = Callable[[], AbstractContextManager[Session]]


@dataclass(frozen=True, slots=True)
class FixedIntervalTicker:
    interval_seconds: float

    async def wait(self) -> None:
        await anyio.sleep(self.interval_seconds)


class MonitoringLifecycle:
    def __init__(self, runner: TickRunner, session_factory: SessionFactory, ticker: LifecycleTicker) -> None:
        self._runner = runner
        self._session_factory = session_factory
        self._ticker = ticker

    async def run(self) -> None:
        while True:
            try:
                with self._session_factory() as session:
                    self._runner.run_tick(session)
            except Exception:
                LOGGER.exception("monitoring scheduler tick failed; continuing after interval")
                record_failure = getattr(self._runner, "record_tick_failure", None)
                if callable(record_failure):
                    record_failure()
            await self._ticker.wait()
