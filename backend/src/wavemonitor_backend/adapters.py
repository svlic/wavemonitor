from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Protocol, TypeAlias

from wavemonitor_backend.data_source_proxy import configure_yfinance_proxy
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
    def all_mids(self, dex: str = "") -> dict[str, str]: ...

    def perp_dexs(self) -> list[dict[str, object] | None]: ...


__all__ = [
    "AdapterError",
    "AdapterErrorKind",
    "BinanceFuturesAdapter",
    "HyperliquidAdapter",
    "PriceResult",
    "YFinanceAdapter",
]


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _normalize_hyperliquid_symbol(symbol: str) -> str:
    normalized = symbol.strip()
    if ":" not in normalized:
        return normalized.upper()
    dex, coin = normalized.split(":", maxsplit=1)
    return f"{dex.lower()}:{coin.upper()}"


def _parse_price(raw_price: object, path: str) -> Decimal | None:
    if raw_price is None:
        return None
    if isinstance(raw_price, Decimal):
        price = raw_price
    elif isinstance(raw_price, bool):
        raise MalformedProviderPriceError(path, raw_price)
    elif isinstance(raw_price, int):
        price = Decimal(raw_price)
    elif isinstance(raw_price, float):
        if not math.isfinite(raw_price):
            raise MalformedProviderPriceError(path, raw_price)
        price = Decimal(str(raw_price))
    elif isinstance(raw_price, str):
        try:
            price = Decimal(raw_price)
        except InvalidOperation as exc:
            raise MalformedProviderPriceError(path, raw_price) from exc
    else:
        try:
            as_float = float(raw_price)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise MalformedProviderPriceError(path, raw_price) from None
        if not math.isfinite(as_float):
            raise MalformedProviderPriceError(path, raw_price)
        price = Decimal(str(as_float))
    if not price.is_finite():
        raise MalformedProviderPriceError(path, raw_price)
    return price


def _error_kind_from_exception(exc: Exception) -> AdapterErrorKind:
    if getattr(exc, "status_code", None) == 429:
        return AdapterErrorKind.RATE_LIMITED
    if isinstance(exc, TimeoutError):
        return AdapterErrorKind.TIMEOUT
    return AdapterErrorKind.PROVIDER_ERROR


def _adapter_error(identity: PriceIdentity, exc: Exception) -> AdapterError:
    if isinstance(exc, MalformedProviderPriceError):
        return AdapterError(
            source=identity.source,
            market_type=identity.market_type,
            symbol=identity.symbol,
            kind=AdapterErrorKind.MALFORMED_PRICE,
            message=str(exc),
            raw_metadata={"path": exc.path, "raw_price": exc.raw_price},
        )
    return AdapterError(
        source=identity.source,
        market_type=identity.market_type,
        symbol=identity.symbol,
        kind=_error_kind_from_exception(exc),
        message=str(exc),
        raw_metadata={"exception_type": type(exc).__name__},
    )


def _price_result(
    identity: PriceIdentity,
    raw_price: object,
    path: str,
    clock: Clock,
) -> PriceResult | None:
    price = _parse_price(raw_price, path)
    if price is None:
        return None
    return PriceResult(
        source=identity.source,
        market_type=identity.market_type,
        symbol=identity.symbol,
        price=price,
        timestamp=clock(),
        raw_metadata={"path": path, "raw_price": raw_price},
    )


class YFinanceAdapter:
    def __init__(
        self,
        *,
        ticker_factory: TickerFactory | None = None,
        clock: Clock = _utc_now,
    ) -> None:
        self._ticker_factory = ticker_factory or self._default_ticker_factory
        self._clock = clock

    def get_latest_price(self, symbol: str, market_type: MarketType) -> PriceAdapterResult:
        _ = market_type
        identity = PriceIdentity(Provider.YFINANCE, MarketType.EQUITY, _normalize_symbol(symbol))
        try:
            ticker = self._ticker_factory(identity.symbol)
            fast_result = self._fast_info_result(identity, ticker.fast_info)
            if fast_result is not None:
                return fast_result
            history_result = self._history_result(identity, ticker)
        except Exception as exc:
            return _adapter_error(identity, exc)
        if history_result is not None:
            return history_result
        return AdapterError(
            identity.source,
            identity.market_type,
            identity.symbol,
            AdapterErrorKind.MISSING_SYMBOL,
            f"{identity.symbol} price was not present in yfinance fast_info or 1m history",
            {"paths": ["fast_info.last_price", "history.close"]},
        )

    def _fast_info_result(self, identity: PriceIdentity, fast_info: object) -> PriceResult | None:
        raw_price = (
            fast_info.get("last_price")
            if isinstance(fast_info, dict)
            else getattr(fast_info, "last_price", None)
        )
        return _price_result(identity, raw_price, "fast_info.last_price", self._clock)

    def _history_result(
        self,
        identity: PriceIdentity,
        ticker: YFinanceTicker,
    ) -> PriceResult | None:
        history = ticker.history(period="1d", interval="1m")
        if bool(getattr(history, "empty", True)):
            return None
        row = history.iloc[-1]
        if isinstance(row, dict):
            raw_price = row.get("Close")
        else:
            raw_price = getattr(row, "get", lambda _key, default=None: default)("Close")
            if raw_price is None and hasattr(row, "__getitem__"):
                try:
                    raw_price = row["Close"]
                except (KeyError, TypeError, IndexError):
                    raw_price = None
        return _price_result(identity, raw_price, "history.close", self._clock)

    def _default_ticker_factory(self, symbol: str) -> YFinanceTicker:
        import yfinance as yf

        configure_yfinance_proxy(yf)
        return yf.Ticker(symbol)


class BinanceFuturesAdapter:
    def __init__(
        self,
        *,
        usd_m_client: BinanceFuturesClient,
        coin_m_client: BinanceFuturesClient,
        clock: Clock = _utc_now,
    ) -> None:
        self._usd_m_client = usd_m_client
        self._coin_m_client = coin_m_client
        self._clock = clock

    def get_latest_price(self, symbol: str, market_type: MarketType) -> PriceAdapterResult:
        identity = PriceIdentity(Provider.BINANCE, market_type, _normalize_symbol(symbol))
        client = self._client_for_market(market_type)
        try:
            mark_result = self._payload_result(
                identity,
                client.mark_price(identity.symbol),
                "markPrice",
                "mark_price.markPrice",
            )
            if mark_result is not None:
                return mark_result
            ticker_result = self._payload_result(
                identity,
                client.ticker_price(identity.symbol),
                "price",
                "ticker_price.price",
            )
        except Exception as exc:
            return _adapter_error(identity, exc)
        if ticker_result is not None:
            return ticker_result
        return AdapterError(
            identity.source,
            identity.market_type,
            identity.symbol,
            AdapterErrorKind.MISSING_SYMBOL,
            f"{identity.symbol} price was not present in Binance mark or latest ticker payloads",
            {"paths": ["mark_price.markPrice", "ticker_price.price"]},
        )

    def _client_for_market(self, market_type: MarketType) -> BinanceFuturesClient:
        if market_type == MarketType.USD_M_FUTURES:
            return self._usd_m_client
        if market_type == MarketType.COIN_M_FUTURES:
            return self._coin_m_client
        raise ValueError(f"unsupported Binance market type: {market_type.value}")

    def _payload_result(
        self,
        identity: PriceIdentity,
        payload: dict[str, object],
        price_key: str,
        path: str,
    ) -> PriceResult | None:
        return _price_result(identity, payload.get(price_key), path, self._clock)


def _hyperliquid_mids_scope(symbol: str) -> tuple[str, str]:
    if ":" not in symbol:
        return "", f"all_mids.{symbol}"
    dex = symbol.split(":", maxsplit=1)[0]
    return dex, f"all_mids.{dex}.{symbol}"


class HyperliquidAdapter:
    def __init__(
        self,
        *,
        info_client: HyperliquidInfoClient,
        clock: Clock = _utc_now,
    ) -> None:
        self._info_client = info_client
        self._clock = clock

    def get_latest_price(self, symbol: str, market_type: MarketType) -> PriceAdapterResult:
        _ = market_type
        identity = PriceIdentity(
            Provider.HYPERLIQUID,
            MarketType.PERPETUAL,
            _normalize_hyperliquid_symbol(symbol),
        )
        dex, path = _hyperliquid_mids_scope(identity.symbol)
        try:
            result = _price_result(
                identity,
                self._info_client.all_mids(dex).get(identity.symbol),
                path,
                self._clock,
            )
        except Exception as exc:
            return _adapter_error(identity, exc)
        if result is None:
            return AdapterError(
                identity.source,
                identity.market_type,
                identity.symbol,
                AdapterErrorKind.MISSING_SYMBOL,
                f"{identity.symbol} price was not present in Hyperliquid all_mids",
                {"path": path},
            )
        return result
