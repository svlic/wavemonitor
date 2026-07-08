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
    def __init__(
        self,
        mids: dict[str, str],
        dexs: list[dict[str, object] | None] | None = None,
        dex_mids: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._mids = mids
        self._dexs = dexs or []
        self._dex_mids = dex_mids or {}

    def all_mids(self, dex: str = "") -> dict[str, str]:
        if not dex:
            return self._mids
        return self._dex_mids.get(dex, {})

    def perp_dexs(self) -> list[dict[str, object] | None]:
        return self._dexs


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
        SymbolOption(
            symbol="BTC",
            label="BTC",
            provider=Provider.HYPERLIQUID,
            market_type=MarketType.PERPETUAL,
        )
    ]


def test_hyperliquid_searches_hip3_stock_contract_dexs() -> None:
    catalog = SymbolCatalog(
        hyperliquid_client=FakeHyperliquid(
            {"BTC": "1"},
            dexs=[{"name": "hip3-stocks"}],
            dex_mids={"hip3-stocks": {"hip3-stocks:AAPL": "1", "hip3-stocks:TSLA": "2"}},
        )
    )
    options = catalog.search(Provider.HYPERLIQUID, MarketType.PERPETUAL, "aa")
    assert options == [
        SymbolOption(
            symbol="hip3-stocks:AAPL",
            label="hip3-stocks:AAPL",
            provider=Provider.HYPERLIQUID,
            market_type=MarketType.PERPETUAL,
        )
    ]


def test_hyperliquid_searches_trade_xyz_assets_from_perp_dex_metadata() -> None:
    catalog = SymbolCatalog(
        hyperliquid_client=FakeHyperliquid(
            {"BTC": "1"},
            dexs=[
                None,
                {
                    "name": "xyz",
                    "fullName": "XYZ",
                    "assetToStreamingOiCap": [
                        ["xyz:AAPL", "100000000.0"],
                        ["xyz:CRCL", "100000000.0"],
                    ],
                },
            ],
        )
    )
    options = catalog.search(Provider.HYPERLIQUID, MarketType.PERPETUAL, "crcl")
    assert options == [
        SymbolOption(
            symbol="xyz:CRCL",
            label="xyz:CRCL",
            provider=Provider.HYPERLIQUID,
            market_type=MarketType.PERPETUAL,
        )
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
