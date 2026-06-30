from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Callable, Protocol, TypeAlias

from wavemonitor_backend.models import MarketType, Provider

RawMetadata: TypeAlias = dict[str, object]
PriceAdapterResult: TypeAlias = "PriceResult | AdapterError"
Clock: TypeAlias = Callable[[], datetime]
TickerFactory: TypeAlias = Callable[[str], "YFinanceTicker"]


class AdapterErrorKind(StrEnum):
    MISSING_SYMBOL = "missing_symbol"
    MALFORMED_PRICE = "malformed_price"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True, slots=True)
class PriceResult:
    source: Provider
    market_type: MarketType
    symbol: str
    price: Decimal
    timestamp: datetime
    raw_metadata: RawMetadata


@dataclass(frozen=True, slots=True)
class AdapterError:
    source: Provider
    market_type: MarketType
    symbol: str
    kind: AdapterErrorKind
    message: str
    raw_metadata: RawMetadata


@dataclass(frozen=True, slots=True)
class PriceIdentity:
    source: Provider
    market_type: MarketType
    symbol: str


@dataclass(frozen=True, slots=True)
class PricePayload:
    path: str
    raw_price: object
    price: Decimal


@dataclass(frozen=True, slots=True)
class MalformedProviderPriceError(Exception):
    path: str
    raw_price: object

    def __str__(self) -> str:
        return f"{self.path} was not a finite decimal string"


class YFinanceTicker(Protocol):
    fast_info: object

    def history(self, *, period: str, interval: str) -> object: ...


class BinanceFuturesClient(Protocol):
    def mark_price(self, symbol: str) -> dict[str, object]: ...

    def ticker_price(self, symbol: str) -> dict[str, object]: ...


class HyperliquidInfoClient(Protocol):
    def all_mids(self) -> dict[str, str]: ...
