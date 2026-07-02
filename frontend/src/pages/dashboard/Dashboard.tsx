import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiError } from "../../api/client";
import type {
  RuntimeResponse,
  LatestPrice,
  RecentAlert,
  SourceError,
  InstrumentWithMappings,
} from "../../api/client";
import { usePollingRefresh } from "../../hooks/usePollingRefresh";
import {
  formatAlertKindLabel,
  formatDateTime,
  formatSourceLabel,
} from "../../utils/format";
import { PriceMonitorPanel } from "./PriceMonitorPanel";

type DashboardState = "loading" | "ready" | "error";

async function fetchDashboardBundle(signal?: AbortSignal) {
  const [runtimeData, pricesData, alertsData, errorsData, instrumentsData] = await Promise.all([
    apiClient.getRuntime(signal),
    apiClient.getLatestPrices(signal),
    apiClient.getRecentAlerts(signal),
    apiClient.getSourceErrors(signal),
    apiClient.getInstruments(signal),
  ]);
  return {
    runtime: runtimeData,
    prices: pricesData,
    alerts: alertsData,
    errors: errorsData,
    instruments: instrumentsData,
  };
}

export function Dashboard() {
  const [state, setState] = useState<DashboardState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const [runtime, setRuntime] = useState<RuntimeResponse | null>(null);
  const [prices, setPrices] = useState<readonly LatestPrice[]>([]);
  const [alerts, setAlerts] = useState<readonly RecentAlert[]>([]);
  const [errors, setErrors] = useState<readonly SourceError[]>([]);
  const [instruments, setInstruments] = useState<readonly InstrumentWithMappings[]>([]);

  const [testStatus, setTestStatus] = useState<"idle" | "sending" | "success" | "error">("idle");
  const [testMessage, setTestMessage] = useState<string | null>(null);

  const applyBundle = useCallback(
    (bundle: Awaited<ReturnType<typeof fetchDashboardBundle>>) => {
      setRuntime(bundle.runtime);
      setPrices(bundle.prices);
      setAlerts(bundle.alerts);
      setErrors(bundle.errors);
      setInstruments(bundle.instruments);
      setState("ready");
      setErrorMessage(null);
    },
    [],
  );

  const loadData = useCallback(
    async (signal?: AbortSignal, options?: { refresh?: boolean }) => {
      const isRefresh = options?.refresh === true;
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setState("loading");
      }
      try {
        const bundle = await fetchDashboardBundle(signal);
        if (signal?.aborted) return;
        applyBundle(bundle);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState("error");
        if (error instanceof ApiError) {
          setErrorMessage(error.message);
        } else {
          setErrorMessage("发生未知错误。");
        }
      } finally {
        if (!signal?.aborted) {
          setRefreshing(false);
        }
      }
    },
    [applyBundle],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  const pollPrices = useCallback(() => {
    void loadData(undefined, { refresh: true });
  }, [loadData]);

  usePollingRefresh(pollPrices, 120_000);

  const handleRefresh = () => {
    void loadData(undefined, { refresh: true });
  };

  const handleTestTelegram = async () => {
    setTestStatus("sending");
    setTestMessage(null);
    try {
      const response = await apiClient.testTelegram();
      if (response.sent) {
        setTestStatus("success");
        setTestMessage("测试消息已发送。");
      } else {
        setTestStatus("error");
        setTestMessage(response.detail || "测试消息发送失败。");
      }
    } catch (error) {
      setTestStatus("error");
      if (error instanceof ApiError) {
        setTestMessage(error.message);
      } else {
        setTestMessage("发生未知错误。");
      }
    }
  };

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
        <button type="button" className="button primary" onClick={handleRefresh}>
          重试加载
        </button>
      </section>
    );
  }

  const getInstrumentName = (id: number) => {
    return instruments.find((i) => i.id === id)?.name ?? String(id);
  };

  const statCards = [
    { label: "启用来源", value: runtime?.enabled_sources ?? 0 },
    { label: "已轮询来源", value: runtime?.polled_sources ?? 0 },
    { label: "写入观测", value: runtime?.observations_written ?? 0 },
    { label: "告警事件", value: runtime?.alert_events_created ?? 0 },
    { label: "来源错误", value: runtime?.source_errors ?? 0 },
    { label: "Telegram 投递", value: runtime?.telegram_deliveries_attempted ?? 0 },
  ];

  const tickMeta = runtime?.last_tick_finished_at
    ? `最近轮询：${formatDateTime(runtime.last_tick_finished_at)}（UTC+8）`
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
              onClick={handleRefresh}
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
            <span className="status-strip__label">调度器</span>
            <span
              className={`status-pill ${runtime?.scheduler_ready ? "status-pill--ready" : "status-pill--idle"}`}
            >
              {runtime?.scheduler_ready ? "就绪" : "未就绪"}
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

      <div className="dashboard-grid">
        <section
          className="panel dashboard-panel--wide dashboard-panel--prices"
          aria-labelledby="prices-title"
        >
          <div className="panel-title-row">
            <div className="panel-title-group">
              <h2 id="prices-title" className="panel-title">
                价格监控
              </h2>
              <p className="muted-text panel-title-sub">
                按标的汇总各来源最新价、距支撑/阻力与盈亏比
              </p>
            </div>
          </div>
          <PriceMonitorPanel prices={prices} instruments={instruments} />
        </section>

        <section className="panel dashboard-panel--telegram" aria-labelledby="telegram-title">
          <h2 id="telegram-title" className="panel-title">
            Telegram
          </h2>
          {!runtime?.telegram_ready ? (
            <p className="muted-text">
              尚未配置。设置 TELEGRAM_BOT_TOKEN 与 TELEGRAM_CHAT_ID 后可推送告警。
            </p>
          ) : (
            <div className="test-actions">
              <button
                className="button primary"
                onClick={() => handleTestTelegram()}
                disabled={testStatus === "sending"}
              >
                {testStatus === "sending" ? "发送中..." : "发送测试告警"}
              </button>
              {testStatus === "success" && (
                <p className="success-text" role="status">
                  {testMessage}
                </p>
              )}
              {testStatus === "error" && (
                <p className="error-text" role="alert">
                  {testMessage}
                </p>
              )}
            </div>
          )}
        </section>

        <section className="panel dashboard-panel--alerts" aria-labelledby="alerts-title">
          <h2 id="alerts-title" className="panel-title">
            最近告警
          </h2>
          {alerts.length === 0 ? (
            <p className="empty-state">暂无最近告警。</p>
          ) : (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>标的</th>
                    <th>规则</th>
                    <th>价格</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((alert) => (
                    <tr key={alert.id}>
                      <td>{formatDateTime(alert.triggered_at)}</td>
                      <td>{getInstrumentName(alert.instrument_id)}</td>
                      <td>{formatAlertKindLabel(alert.alert_kind)}</td>
                      <td className="price-cell">{alert.price}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel dashboard-panel--errors" aria-labelledby="errors-title">
          <h2 id="errors-title" className="panel-title">
            数据源错误
          </h2>
          {errors.length === 0 ? (
            <p className="empty-state">暂无数据源错误。</p>
          ) : (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>标的</th>
                    <th>来源</th>
                    <th>错误</th>
                  </tr>
                </thead>
                <tbody>
                  {errors.map((error) => (
                    <tr key={error.source_mapping_id}>
                      <td>{formatDateTime(error.last_observed_at)}</td>
                      <td>{error.instrument_name}</td>
                      <td>{formatSourceLabel(error.provider, error.market_type, error.symbol)}</td>
                      <td className="error-cell">{error.last_error}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}