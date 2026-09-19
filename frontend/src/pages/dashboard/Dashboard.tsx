import { useEffect } from "react";
import { apiClient } from "../../api/client";
import { useLoadData } from "../../hooks/useLoadData";
import { formatDateTime } from "../../utils/format";
import { PriceMonitorPanel } from "./PriceMonitorPanel";

function loadDashboardData(signal?: AbortSignal) {
  return Promise.all([
    apiClient.getRuntime(signal),
    apiClient.getLatestPrices(signal),
    apiClient.getInstruments(signal),
  ]);
}

export function Dashboard() {
  const { state, errorMessage, refreshing, data, refresh } = useLoadData(loadDashboardData);
  const [runtime, prices, instruments] = data ?? [null, [], []];

  useEffect(() => {
    const id = window.setInterval(refresh, 120_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  if (state === "loading") {
    return (
      <section className="panel loading-panel" aria-labelledby="dashboard-loading-title">
        <h2 id="dashboard-loading-title" className="visually-hidden">
          仪表盘
        </h2>
        <div role="status" aria-live="polite" className="muted-text">
          正在加载仪表盘数据...
        </div>
        <div className="skeleton skeleton-line skeleton-line--medium" aria-hidden="true" />
        <div className="skeleton skeleton-line" aria-hidden="true" />
        <div className="skeleton skeleton-block" aria-hidden="true" />
      </section>
    );
  }

  if (state === "error") {
    return (
      <section className="panel" aria-labelledby="dashboard-error-title">
        <h2 id="dashboard-error-title" className="visually-hidden">
          仪表盘
        </h2>
        <div className="error-banner" role="alert">
          <p className="error-text">{errorMessage ?? "仪表盘加载失败。"}</p>
        </div>
        <button type="button" className="button primary" onClick={refresh}>
          重试加载
        </button>
      </section>
    );
  }

  const statCards = [
    { label: "启用来源", value: runtime?.enabled_sources ?? 0 },
    { label: "已轮询来源", value: runtime?.polled_sources ?? 0 },
    { label: "写入观测", value: runtime?.observations_written ?? 0 },
    { label: "告警事件", value: runtime?.alert_events_created ?? 0 },
    { label: "来源错误", value: runtime?.source_errors ?? 0 },
    { label: "Telegram 投递", value: runtime?.telegram_deliveries_attempted ?? 0 },
  ];

  const tickMeta = runtime?.last_tick_finished_at
    ? `最近轮询：${formatDateTime(runtime.last_tick_finished_at)}`
    : "尚未完成轮询周期";

  return (
    <div className="dashboard-layout">
      <header className="dashboard-overview panel" aria-label="运行概览">
        <div className="dashboard-overview__head">
          <p className="dashboard-overview__meta muted-text">{tickMeta}</p>
          <div className="dashboard-overview__actions">
            <span className="muted-text dashboard-overview__hint">价格每 2 分钟自动刷新</span>
            <button
              type="button"
              className="button small"
              onClick={refresh}
              disabled={refreshing}
              aria-busy={refreshing}
            >
              {refreshing ? "刷新中..." : "刷新数据"}
            </button>
          </div>
        </div>
        <div className="stat-grid" role="list">
          {statCards.map((card) => (
            <div key={card.label} className="stat-card" role="listitem">
              <span className="stat-card__label">{card.label}</span>
              <span className="stat-card__value">{card.value}</span>
            </div>
          ))}
        </div>
        <div className="status-strip" role="list" aria-label="组件就绪状态">
          <div className="status-strip__item" role="listitem">
            <span className="status-strip__label">轮询调度</span>
            <span
              className={`status-pill ${runtime?.scheduler_ready ? "status-pill--ready" : "status-pill--idle"}`}
            >
              {runtime?.scheduler_ready ? "已运行" : "等待首次轮询"}
            </span>
          </div>
          <div className="status-strip__item" role="listitem">
            <span className="status-strip__label">数据源</span>
            <span
              className={`status-pill ${runtime?.providers_ready ? "status-pill--ready" : "status-pill--idle"}`}
            >
              {runtime?.providers_ready ? "就绪" : "未就绪"}
            </span>
          </div>
          <div className="status-strip__item" role="listitem">
            <span className="status-strip__label">Telegram</span>
            <span
              className={`status-pill ${runtime?.telegram_ready ? "status-pill--ready" : "status-pill--idle"}`}
            >
              {runtime?.telegram_ready ? "就绪" : "未配置"}
            </span>
          </div>
        </div>
      </header>

      <section
        className="panel dashboard-panel--prices dashboard-panel--wide"
        aria-labelledby="prices-title"
      >
        <h2 id="prices-title" className="panel-title panel-title--inline">
          价格监控
          <span className="muted-text panel-title-sub panel-title-sub--inline">
            全宽表格 · 各来源最新价 · 距支撑/阻力 · 盈亏比
          </span>
        </h2>
        <PriceMonitorPanel prices={prices} instruments={instruments} />
      </section>
    </div>
  );
}
