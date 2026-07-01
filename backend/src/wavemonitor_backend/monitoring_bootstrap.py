from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

from sqlalchemy import Engine

from wavemonitor_backend.adapters import BinanceFuturesAdapter, HyperliquidAdapter, YFinanceAdapter
from wavemonitor_backend.symbol_catalog import SymbolCatalog, default_symbol_catalog
from wavemonitor_backend.db import session_scope
from wavemonitor_backend.lifecycle import FixedIntervalTicker, MonitoringLifecycle
from wavemonitor_backend.models import MarketType, Provider
from wavemonitor_backend.monitoring import AdapterRegistry, MonitoringScheduler, RuntimeMetricsStore, SourcePoller
from wavemonitor_backend.notifier import TelegramNotifier
from wavemonitor_backend.settings import Settings

POLL_INTERVAL_SECONDS_ENV: Final[str] = "WAVEMONITOR_POLL_INTERVAL_SECONDS"
DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 60.0
MONITORING_DISABLED_ENV: Final[str] = "WAVEMONITOR_MONITORING_DISABLED"


def poll_interval_seconds_from_env() -> float:
    raw = os.getenv(POLL_INTERVAL_SECONDS_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_POLL_INTERVAL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_POLL_INTERVAL_SECONDS
    return value if value > 0 else DEFAULT_POLL_INTERVAL_SECONDS


def monitoring_disabled_from_env() -> bool:
    return os.getenv(MONITORING_DISABLED_ENV, "").strip().lower() in {"1", "true", "yes"}


def build_adapter_registry() -> AdapterRegistry:
    from binance.cm_futures import CMFutures
    from binance.um_futures import UMFutures
    from hyperliquid.info import Info

    usd_m = UMFutures()
    coin_m = CMFutures()
    return AdapterRegistry(
        adapters={
            (Provider.YFINANCE, MarketType.EQUITY): YFinanceAdapter(),
            (
                Provider.BINANCE,
                MarketType.USD_M_FUTURES,
            ): BinanceFuturesAdapter(usd_m_client=usd_m, coin_m_client=coin_m),
            (
                Provider.BINANCE,
                MarketType.COIN_M_FUTURES,
            ): BinanceFuturesAdapter(usd_m_client=usd_m, coin_m_client=coin_m),
            (Provider.HYPERLIQUID, MarketType.PERPETUAL): HyperliquidAdapter(info_client=Info()),
        }
    )


def build_symbol_catalog() -> SymbolCatalog:
    return default_symbol_catalog()


def build_monitoring_lifecycle(
    *,
    engine: Engine,
    settings: Settings,
    metrics_store: RuntimeMetricsStore,
    poll_interval_seconds: float | None = None,
) -> MonitoringLifecycle:
    registry = build_adapter_registry()
    notifier = TelegramNotifier(settings)
    scheduler = MonitoringScheduler(SourcePoller(registry), notifier, metrics_store=metrics_store)

    @contextmanager
    def session_factory() -> Iterator:
        with session_scope(engine) as session:
            yield session

    interval = poll_interval_seconds if poll_interval_seconds is not None else poll_interval_seconds_from_env()
    return MonitoringLifecycle(scheduler, session_factory, FixedIntervalTicker(interval_seconds=interval))


def default_monitoring_lifecycle(
    *,
    engine: Engine,
    settings: Settings,
    metrics_store: RuntimeMetricsStore,
) -> MonitoringLifecycle | None:
    if monitoring_disabled_from_env():
        return None
    return build_monitoring_lifecycle(engine=engine, settings=settings, metrics_store=metrics_store)