from __future__ import annotations

import pytest

from wavemonitor_backend.data_source_proxy import DATA_SOURCE_SOCKS5_PROXY_ENV
from wavemonitor_backend.models import MarketType, Provider
from wavemonitor_backend.symbol_catalog import (
    BINANCE_TIMEOUT_SECONDS,
    SymbolCatalog,
    SymbolOption,
    default_binance_futures_clients,
)


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


class UnavailableBinanceExchange:
    def exchange_info(self) -> dict[str, object]:
        raise RuntimeError("provider unavailable")


class FakeBinanceSdkClient:
    created_with: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        self.created_with.append(kwargs)

    def exchange_info(self) -> dict[str, object]:
        return {"symbols": []}


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


@pytest.mark.parametrize("query", ["btc", " BTC ", "\t bTc\n"])
def test_binance_filters_trading_symbols_and_ranks_prefix_matches(query: str) -> None:
    catalog = SymbolCatalog(
        usd_m_client=FakeBinanceExchange(["ETHUSDT", "BTCUSDT", "HALTED", "WBTCUSDT"]),
    )
    options = catalog.search(Provider.BINANCE, MarketType.USD_M_FUTURES, query)
    assert [option.symbol for option in options] == ["BTCUSDT", "WBTCUSDT"]


def test_binance_falls_back_to_normalized_usd_m_symbol_when_catalog_is_unavailable() -> None:
    catalog = SymbolCatalog(usd_m_client=UnavailableBinanceExchange())

    options = catalog.search(Provider.BINANCE, MarketType.USD_M_FUTURES, "btcusdt")

    assert options == [
        SymbolOption(
            symbol="BTCUSDT",
            label="BTCUSDT",
            provider=Provider.BINANCE,
            market_type=MarketType.USD_M_FUTURES,
        )
    ]


def test_binance_fallback_appends_usdt_for_partial_usd_m_symbol() -> None:
    catalog = SymbolCatalog(usd_m_client=UnavailableBinanceExchange())

    options = catalog.search(Provider.BINANCE, MarketType.USD_M_FUTURES, "btc")

    assert options[0].symbol == "BTCUSDT"


def test_binance_fallback_preserves_coin_m_contract_query() -> None:
    catalog = SymbolCatalog(coin_m_client=UnavailableBinanceExchange())

    options = catalog.search(Provider.BINANCE, MarketType.COIN_M_FUTURES, "btcusd_perp")

    assert options[0].symbol == "BTCUSD_PERP"


def test_default_binance_clients_do_not_set_empty_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    from binance import cm_futures, um_futures

    FakeBinanceSdkClient.created_with.clear()
    monkeypatch.delenv(DATA_SOURCE_SOCKS5_PROXY_ENV, raising=False)
    monkeypatch.setattr(um_futures, "UMFutures", FakeBinanceSdkClient)
    monkeypatch.setattr(cm_futures, "CMFutures", FakeBinanceSdkClient)

    default_binance_futures_clients()

    assert FakeBinanceSdkClient.created_with == [
        {"timeout": BINANCE_TIMEOUT_SECONDS},
        {"timeout": BINANCE_TIMEOUT_SECONDS},
    ]


def test_default_binance_clients_use_data_source_socks5_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from binance import cm_futures, um_futures

    FakeBinanceSdkClient.created_with.clear()
    monkeypatch.setenv(DATA_SOURCE_SOCKS5_PROXY_ENV, " socks5h://proxy.internal:1080 ")
    monkeypatch.setattr(um_futures, "UMFutures", FakeBinanceSdkClient)
    monkeypatch.setattr(cm_futures, "CMFutures", FakeBinanceSdkClient)

    default_binance_futures_clients()

    expected = {
        "timeout": BINANCE_TIMEOUT_SECONDS,
        "proxies": {
            "http": "socks5h://proxy.internal:1080",
            "https": "socks5h://proxy.internal:1080",
        },
    }
    assert FakeBinanceSdkClient.created_with == [expected, expected]


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


@pytest.mark.parametrize("query", ["aapl", " AaPl\t", "\u3000aapl\u3000"])
def test_yfinance_uses_injected_search_factory(query: str) -> None:
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
    options = catalog.search(Provider.YFINANCE, MarketType.EQUITY, query)
    assert len(options) == 1
    assert options[0].symbol == "AAPL"


@pytest.mark.parametrize("query", ["", " \t\n", "\u3000"])
def test_blank_query_does_not_call_provider(query: str) -> None:
    def unexpected_search(_query: str, _limit: int) -> list[SymbolOption]:
        pytest.fail("A blank query must not call the provider")

    catalog = SymbolCatalog(yfinance_search=unexpected_search)
    assert catalog.search(Provider.YFINANCE, MarketType.EQUITY, query) == []
