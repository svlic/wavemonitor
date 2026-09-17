from __future__ import annotations

import os
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from typing import Final, Protocol

DATA_SOURCE_SOCKS5_PROXY_ENV: Final[str] = "WAVEMONITOR_SOCKS5_PROXY"
_SOCKS5_SCHEMES: Final[tuple[str, ...]] = ("socks5://", "socks5h://")


class YFinanceNetworkConfig(Protocol):
    proxy: str


class YFinanceConfig(Protocol):
    network: YFinanceNetworkConfig


class YFinanceModule(Protocol):
    config: YFinanceConfig


class ProxySession(Protocol):
    proxies: MutableMapping[str, str]


class HyperliquidInfoClient(Protocol):
    session: ProxySession

    def all_mids(self, dex: str = "") -> dict[str, str]: ...

    def perp_dexs(self) -> list[dict[str, object] | None]: ...


def data_source_socks5_proxy() -> str | None:
    proxy = os.getenv(DATA_SOURCE_SOCKS5_PROXY_ENV, "").strip()
    if not proxy:
        return None
    if not proxy.lower().startswith(_SOCKS5_SCHEMES):
        raise ValueError(
            f"{DATA_SOURCE_SOCKS5_PROXY_ENV} must use a socks5:// or socks5h:// URL"
        )
    return proxy


def proxy_mapping(proxy: str) -> dict[str, str]:
    return {"http": proxy, "https": proxy}


def configure_yfinance_proxy(yfinance: YFinanceModule) -> None:
    proxy = data_source_socks5_proxy()
    if proxy is not None:
        yfinance.config.network.proxy = proxy


@contextmanager
def hyperliquid_proxy_environment() -> Iterator[str | None]:
    proxy = data_source_socks5_proxy()
    if proxy is None:
        yield None
        return

    previous = {name: os.environ.get(name) for name in ("ALL_PROXY", "all_proxy")}
    os.environ.update({name: proxy for name in previous})
    try:
        yield proxy
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def default_hyperliquid_info_client() -> HyperliquidInfoClient:
    from hyperliquid.info import Info

    with hyperliquid_proxy_environment() as proxy:
        client = Info(skip_ws=True)
    if proxy is not None:
        client.session.proxies.update(proxy_mapping(proxy))
    return client
