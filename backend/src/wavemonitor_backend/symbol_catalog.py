from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Final, Protocol

from wavemonitor_backend.adapters import BinanceFuturesClient, HyperliquidInfoClient
from wavemonitor_backend.data_source_proxy import (
    configure_yfinance_proxy,
    data_source_socks5_proxy,
    default_hyperliquid_info_client,
    proxy_mapping,
)
from wavemonitor_backend.models import MarketType, Provider

SYMBOL_QUERY_MAX_RESULTS: Final[int] = 25
BINANCE_TIMEOUT_SECONDS: Final[int] = 5


@dataclass(frozen=True, slots=True)
class SymbolOption:
    symbol: str
    label: str
    provider: Provider
    market_type: MarketType


class BinanceExchangeListing(BinanceFuturesClient, Protocol):
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
    symbols: Iterable[str],
    *,
    query: str,
    provider: Provider,
    market_type: MarketType,
    limit: int,
) -> list[SymbolOption]:
    matches = list({symbol for symbol in symbols if query in symbol.upper()})
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


def _binance_fallback_option(
    query: str,
    *,
    provider: Provider,
    market_type: MarketType,
) -> list[SymbolOption]:
    symbol = query
    if market_type is MarketType.USD_M_FUTURES and not symbol.endswith("USDT"):
        symbol = f"{symbol}USDT"
    return [
        SymbolOption(
            symbol=symbol,
            label=symbol,
            provider=provider,
            market_type=market_type,
        )
    ]


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
            return _binance_fallback_option(query, provider=provider, market_type=market_type)
        try:
            payload = client.exchange_info()
        except Exception:
            return _binance_fallback_option(query, provider=provider, market_type=market_type)
        if not isinstance(payload, dict):
            return _binance_fallback_option(query, provider=provider, market_type=market_type)
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
        symbols = self._hyperliquid_symbols()
        return _filter_symbols(
            symbols,
            query=query,
            provider=provider,
            market_type=market_type,
            limit=SYMBOL_QUERY_MAX_RESULTS,
        )

    def _hyperliquid_symbols(self) -> list[str]:
        if self._hyperliquid_client is None:
            return []
        symbols = list(self._hyperliquid_mids_for_dex("").keys())
        for dex in self._hyperliquid_dexs():
            name = _hyperliquid_dex_name(dex)
            if name is not None:
                symbols.extend(self._hyperliquid_mids_for_dex(name).keys())
            symbols.extend(_hyperliquid_dex_assets(dex))
        return symbols

    def _hyperliquid_dexs(self) -> list[dict[str, object]]:
        if self._hyperliquid_client is None:
            return []
        try:
            dexs = self._hyperliquid_client.perp_dexs()
        except Exception:
            return []
        return [dex for dex in dexs if isinstance(dex, dict)]

    def _hyperliquid_mids_for_dex(self, dex: str) -> dict[str, str]:
        if self._hyperliquid_client is None:
            return {}
        try:
            return self._hyperliquid_client.all_mids(dex)
        except Exception:
            return {}


def _hyperliquid_dex_name(dex: dict[str, object]) -> str | None:
    name = dex.get("name")
    return name if isinstance(name, str) and name else None


def _hyperliquid_dex_assets(dex: dict[str, object]) -> list[str]:
    assets: list[str] = []
    for key in ("assetToStreamingOiCap", "assetToFundingMultiplier", "assetToFundingInterestRate"):
        entries = dex.get(key)
        if not isinstance(entries, list):
            continue
        assets.extend(_hyperliquid_asset_names(entries))
    return assets


def _hyperliquid_asset_names(entries: list[object]) -> list[str]:
    names: list[str] = []
    for entry in entries:
        if not isinstance(entry, list) or not entry:
            continue
        asset = entry[0]
        if isinstance(asset, str) and asset:
            names.append(asset)
    return names


def _default_yfinance_search(query: str, limit: int) -> list[SymbolOption]:

    import yfinance as yf

    configure_yfinance_proxy(yf)
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


def default_binance_futures_clients() -> tuple[BinanceExchangeListing, BinanceExchangeListing]:
    from binance.cm_futures import CMFutures
    from binance.um_futures import UMFutures

    kwargs: dict[str, object] = {"timeout": BINANCE_TIMEOUT_SECONDS}
    socks5_proxy = data_source_socks5_proxy()
    if socks5_proxy is not None:
        kwargs["proxies"] = proxy_mapping(socks5_proxy)
    return UMFutures(**kwargs), CMFutures(**kwargs)


def default_symbol_catalog() -> SymbolCatalog:
    usd_m, coin_m = default_binance_futures_clients()
    return SymbolCatalog(
        usd_m_client=usd_m,
        coin_m_client=coin_m,
        hyperliquid_client=default_hyperliquid_info_client(),
    )
