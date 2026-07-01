from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Final, Protocol

from wavemonitor_backend.adapter_types import HyperliquidInfoClient
from wavemonitor_backend.models import MarketType, Provider

SYMBOL_QUERY_MAX_RESULTS: Final[int] = 25


@dataclass(frozen=True, slots=True)
class SymbolOption:
    symbol: str
    label: str
    provider: Provider
    market_type: MarketType


class BinanceExchangeListing(Protocol):
    def exchange_info(self) -> dict[str, object]: ...


YFinanceSearchFactory = Callable[[str, int], list[SymbolOption]]


def _normalize_query(query: str) -> str:
    return query.strip().upper()


def _rank_key(symbol: str, query: str) -> tuple[int, str]:
    upper = symbol.upper()
    if upper.startswith(query):
        return (0, upper)
    if upper.endswith(query):
        return (1, upper)
    return (2, upper)


def _filter_symbols(
    symbols: list[str],
    *,
    query: str,
    provider: Provider,
    market_type: MarketType,
    limit: int,
) -> list[SymbolOption]:
    matches = [symbol for symbol in symbols if query in symbol.upper()]
    matches.sort(key=lambda symbol: _rank_key(symbol, query))
    return [
        SymbolOption(symbol=symbol, label=symbol, provider=provider, market_type=market_type)
        for symbol in matches[:limit]
    ]


def _binance_trading_symbols(payload: dict[str, object]) -> list[str]:
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, list):
        return []
    symbols: list[str] = []
    for entry in raw_symbols:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") != "TRADING":
            continue
        symbol = entry.get("symbol")
        if isinstance(symbol, str) and symbol:
            symbols.append(symbol)
    return symbols


class SymbolCatalog:
    def __init__(
        self,
        *,
        usd_m_client: BinanceExchangeListing | None = None,
        coin_m_client: BinanceExchangeListing | None = None,
        hyperliquid_client: HyperliquidInfoClient | None = None,
        yfinance_search: YFinanceSearchFactory | None = None,
    ) -> None:
        self._usd_m_client = usd_m_client
        self._coin_m_client = coin_m_client
        self._hyperliquid_client = hyperliquid_client
        self._yfinance_search = yfinance_search or _default_yfinance_search

    def search(self, provider: Provider, market_type: MarketType, query: str) -> list[SymbolOption]:
        normalized = _normalize_query(query)
        if not normalized:
            return []
        match (provider, market_type):
            case (Provider.BINANCE, MarketType.USD_M_FUTURES):
                return self._search_binance(
                    self._usd_m_client,
                    query=normalized,
                    provider=provider,
                    market_type=market_type,
                )
            case (Provider.BINANCE, MarketType.COIN_M_FUTURES):
                return self._search_binance(
                    self._coin_m_client,
                    query=normalized,
                    provider=provider,
                    market_type=market_type,
                )
            case (Provider.HYPERLIQUID, MarketType.PERPETUAL):
                return self._search_hyperliquid(normalized, provider, market_type)
            case (Provider.YFINANCE, MarketType.EQUITY):
                return self._yfinance_search(normalized, SYMBOL_QUERY_MAX_RESULTS)
            case _:
                return []

    def _search_binance(
        self,
        client: BinanceExchangeListing | None,
        *,
        query: str,
        provider: Provider,
        market_type: MarketType,
    ) -> list[SymbolOption]:
        if client is None:
            return []
        try:
            payload = client.exchange_info()
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []
        return _filter_symbols(
            _binance_trading_symbols(payload),
            query=query,
            provider=provider,
            market_type=market_type,
            limit=SYMBOL_QUERY_MAX_RESULTS,
        )

    def _search_hyperliquid(
        self,
        query: str,
        provider: Provider,
        market_type: MarketType,
    ) -> list[SymbolOption]:
        if self._hyperliquid_client is None:
            return []
        try:
            mids = self._hyperliquid_client.all_mids()
        except Exception:
            return []
        return _filter_symbols(
            list(mids.keys()),
            query=query,
            provider=provider,
            market_type=market_type,
            limit=SYMBOL_QUERY_MAX_RESULTS,
        )


def _default_yfinance_search(query: str, limit: int) -> list[SymbolOption]:
    import yfinance as yf

    try:
        quotes = yf.Search(query, max_results=limit).quotes
    except Exception:
        return []
    options: list[SymbolOption] = []
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        symbol = quote.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            continue
        label = quote.get("shortname") or quote.get("longname") or symbol
        if not isinstance(label, str):
            label = symbol
        options.append(
            SymbolOption(
                symbol=symbol.strip().upper(),
                label=f"{symbol} — {label}" if label != symbol else symbol,
                provider=Provider.YFINANCE,
                market_type=MarketType.EQUITY,
            )
        )
    return options[:limit]


def default_symbol_catalog() -> SymbolCatalog:
    from binance.cm_futures import CMFutures
    from binance.um_futures import UMFutures
    from hyperliquid.info import Info

    return SymbolCatalog(
        usd_m_client=UMFutures(),
        coin_m_client=CMFutures(),
        hyperliquid_client=Info(),
    )