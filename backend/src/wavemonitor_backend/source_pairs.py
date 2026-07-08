from __future__ import annotations

from typing import Final

from wavemonitor_backend.models import MarketType, Provider

ALLOWED_PROVIDER_MARKET_PAIRS: Final[frozenset[tuple[Provider, MarketType]]] = frozenset(
    {
        (Provider.YFINANCE, MarketType.EQUITY),
        (Provider.BINANCE, MarketType.USD_M_FUTURES),
        (Provider.BINANCE, MarketType.COIN_M_FUTURES),
        (Provider.HYPERLIQUID, MarketType.PERPETUAL),
    }
)


def validate_provider_market_pair(provider: Provider, market_type: MarketType) -> None:
    if (provider, market_type) not in ALLOWED_PROVIDER_MARKET_PAIRS:
        raise ValueError(
            f"market_type {market_type.value!r} is not supported for provider {provider.value!r}"
        )
