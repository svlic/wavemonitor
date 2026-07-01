from __future__ import annotations

from wavemonitor_backend.models import MarketType, Provider
from wavemonitor_backend.symbol_catalog import SymbolCatalog, SymbolOption


class FakeBinanceExchange:
    def __init__(self, symbols: list[str]) -> None:
        self._symbols = symbols

    def exchange_info(self) -> dict[str, object]:
        return {
            "symbols": [
                {"symbol": symbol, "status": "TRADING" if symbol != "HALTED" else "BREAK"}
                for symbol in self._symbols
            ]
        }


class FakeHyperliquid:
    def __init__(self, mids: dict[str, str]) -> None:
        self._mids = mids

    def all_mids(self) -> dict[str, str]:
        return self._mids


def test_binance_filters_trading_symbols_and_ranks_prefix_matches() -> None:
    catalog = SymbolCatalog(
        usd_m_client=FakeBinanceExchange(["ETHUSDT", "BTCUSDT", "HALTED", "WBTCUSDT"]),
    )
    options = catalog.search(Provider.BINANCE, MarketType.USD_M_FUTURES, "btc")
    assert [option.symbol for option in options] == ["BTCUSDT", "WBTCUSDT"]


def test_hyperliquid_searches_all_mids() -> None:
    catalog = SymbolCatalog(hyperliquid_client=FakeHyperliquid({"BTC": "1", "ETH": "2"}))
    options = catalog.search(Provider.HYPERLIQUID, MarketType.PERPETUAL, "bt")
    assert options == [
        SymbolOption(symbol="BTC", label="BTC", provider=Provider.HYPERLIQUID, market_type=MarketType.PERPETUAL)
    ]


def test_yfinance_uses_injected_search_factory() -> None:
    def fake_search(query: str, limit: int) -> list[SymbolOption]:
        assert query == "AAPL"
        assert limit == 25
        return [
            SymbolOption(
                symbol="AAPL",
                label="AAPL — Apple Inc.",
                provider=Provider.YFINANCE,
                market_type=MarketType.EQUITY,
            )
        ]

    catalog = SymbolCatalog(yfinance_search=fake_search)
    options = catalog.search(Provider.YFINANCE, MarketType.EQUITY, "aapl")
    assert len(options) == 1
    assert options[0].symbol == "AAPL"