from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from threading import Lock


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    price: Decimal
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class SourcePriceStatus:
    latest_success: PriceSnapshot | None = None
    last_attempt_at: datetime | None = None
    last_error: str | None = None


class LatestPriceStore:
    def __init__(self) -> None:
        self._statuses: dict[int, SourcePriceStatus] = {}
        self._lock = Lock()

    def record_success(self, source_id: int, *, price: Decimal, observed_at: datetime) -> None:
        with self._lock:
            self._statuses[source_id] = SourcePriceStatus(
                latest_success=PriceSnapshot(price=price, observed_at=observed_at),
                last_attempt_at=observed_at,
                last_error=None,
            )

    def record_error(self, source_id: int, *, error: str, observed_at: datetime) -> None:
        with self._lock:
            previous = self._statuses.get(source_id)
            self._statuses[source_id] = SourcePriceStatus(
                latest_success=previous.latest_success if previous is not None else None,
                last_attempt_at=observed_at,
                last_error=error,
            )

    def get(self, source_id: int) -> SourcePriceStatus | None:
        with self._lock:
            return self._statuses.get(source_id)

    def remove(self, source_ids: set[int]) -> None:
        with self._lock:
            for source_id in source_ids:
                self._statuses.pop(source_id, None)
