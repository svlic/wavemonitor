from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from wavemonitor_backend.data_source_proxy import (
    DATA_SOURCE_SOCKS5_PROXY_ENV,
    configure_yfinance_proxy,
    data_source_socks5_proxy,
    default_hyperliquid_info_client,
)


def test_proxy_rejects_non_socks5_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATA_SOURCE_SOCKS5_PROXY_ENV, "http://proxy.internal:8080")

    with pytest.raises(ValueError, match="must use a socks5:// or socks5h:// URL"):
        data_source_socks5_proxy()


def test_yfinance_uses_configured_socks5_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATA_SOURCE_SOCKS5_PROXY_ENV, " socks5h://proxy.internal:1080 ")
    yfinance = SimpleNamespace(config=SimpleNamespace(network=SimpleNamespace(proxy=None)))

    configure_yfinance_proxy(yfinance)

    assert yfinance.config.network.proxy == "socks5h://proxy.internal:1080"


def test_hyperliquid_uses_proxy_during_construction_and_for_rest_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hyperliquid import info

    observed: dict[str, object] = {}

    class FakeInfo:
        def __init__(self, *, skip_ws: bool) -> None:
            observed["skip_ws"] = skip_ws
            observed["constructor_proxy"] = os.environ.get("ALL_PROXY")
            self.session = SimpleNamespace(proxies={})

        def all_mids(self, dex: str = "") -> dict[str, str]:
            return {}

        def perp_dexs(self) -> list[dict[str, object] | None]:
            return []

    lower_proxy_env = "all_proxy"
    monkeypatch.setenv(DATA_SOURCE_SOCKS5_PROXY_ENV, "socks5://proxy.internal:1080")
    monkeypatch.setenv("ALL_PROXY", "http://existing.internal:8080")
    monkeypatch.setenv(lower_proxy_env, "http://existing-lower.internal:8080")
    monkeypatch.setattr(info, "Info", FakeInfo)

    client = default_hyperliquid_info_client()

    assert observed == {
        "skip_ws": True,
        "constructor_proxy": "socks5://proxy.internal:1080",
    }
    assert client.session.proxies == {
        "http": "socks5://proxy.internal:1080",
        "https": "socks5://proxy.internal:1080",
    }
    assert os.environ["ALL_PROXY"] == "http://existing.internal:8080"
    assert os.environ[lower_proxy_env] == "http://existing-lower.internal:8080"
