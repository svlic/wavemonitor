import { useEffect, useState } from "react";
import { apiClient, ApiError } from "../../api/client";
import type { RuntimeResponse, LatestPrice, RecentAlert, SourceError, InstrumentWithMappings } from "../../api/client";

type DashboardState = "loading" | "ready" | "error";

export function Dashboard() {
  const [state, setState] = useState<DashboardState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  
  const [runtime, setRuntime] = useState<RuntimeResponse | null>(null);
  const [prices, setPrices] = useState<readonly LatestPrice[]>([]);
  const [alerts, setAlerts] = useState<readonly RecentAlert[]>([]);
  const [errors, setErrors] = useState<readonly SourceError[]>([]);
  const [instruments, setInstruments] = useState<readonly InstrumentWithMappings[]>([]);

  const [testStatus, setTestStatus] = useState<"idle" | "sending" | "success" | "error">("idle");
  const [testMessage, setTestMessage] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadData() {
      try {
        const [runtimeData, pricesData, alertsData, errorsData, instrumentsData] = await Promise.all([
          apiClient.getRuntime(controller.signal),
          apiClient.getLatestPrices(controller.signal),
          apiClient.getRecentAlerts(controller.signal),
          apiClient.getSourceErrors(controller.signal),
          apiClient.getInstruments(controller.signal),
        ]);

        setRuntime(runtimeData);
        setPrices(pricesData);
        setAlerts(alertsData);
        setErrors(errorsData);
        setInstruments(instrumentsData);
        setState("ready");
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
      }
    }

    loadData();

    return () => {
      controller.abort();
    };
  }, []);

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
      <section className="panel loading-panel" aria-labelledby="dashboard-title">
        <h1 id="dashboard-title">仪表盘</h1>
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
      <section className="panel" aria-labelledby="dashboard-title">
        <h1 id="dashboard-title">仪表盘</h1>
        <div className="error-banner" role="alert">
          <p className="error-text">{errorMessage ?? "仪表盘加载失败。"}</p>
        </div>
      </section>
    );
  }

  const getInstrumentName = (id: number) => {
    return instruments.find((i) => i.id === id)?.name ?? String(id);
  };

  const formatSourceLabel = (provider: string, marketType: string, symbol: string) => {
    return `${provider} (${marketType} ${symbol})`;
  };

  return (
    <div className="dashboard-layout">
      <div className="dashboard-header">
        <h1 id="dashboard-title">仪表盘</h1>
      </div>

      <div className="dashboard-grid">
        <section className="panel" aria-labelledby="status-title">
          <h2 id="status-title" className="panel-title">系统状态</h2>
          <ul className="status-list">
            <li>
              <span className="status-label">调度器：</span>
              <span className={`status-value ${runtime?.scheduler_ready ? 'ready' : 'not-ready'}`}>
                {runtime?.scheduler_ready ? "就绪" : "未就绪"}
              </span>
            </li>
            <li>
              <span className="status-label">数据源：</span>
              <span className={`status-value ${runtime?.providers_ready ? 'ready' : 'not-ready'}`}>
                {runtime?.providers_ready ? "就绪" : "未就绪"}
              </span>
            </li>
            <li>
              <span className="status-label">Telegram：</span>
              <span className={`status-value ${runtime?.telegram_ready ? 'ready' : 'not-ready'}`}>
                {runtime?.telegram_ready ? "就绪" : "未配置"}
              </span>
            </li>
          </ul>

          <div className="telegram-test-section">
            <h3>Telegram 测试</h3>
            {!runtime?.telegram_ready ? (
              <p className="muted-text">
                Telegram 尚未配置。设置 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID 环境变量后即可启用告警通知。
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
                {testStatus === "success" && <p className="success-text" role="status">{testMessage}</p>}
                {testStatus === "error" && <p className="error-text" role="alert">{testMessage}</p>}
              </div>
            )}
          </div>
        </section>

        <section className="panel" aria-labelledby="prices-title">
          <h2 id="prices-title" className="panel-title">最新价格</h2>
          {prices.length === 0 ? (
            <p className="empty-state">暂无价格数据。</p>
          ) : (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>标的</th>
                    <th>来源</th>
                    <th>价格</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {prices.map((price) => (
                    <tr key={price.source_mapping_id}>
                      <td>{price.instrument_name}</td>
                      <td>{formatSourceLabel(price.provider, price.market_type, price.symbol)}</td>
                      <td className="price-cell">{price.last_price}</td>
                      <td>{new Date(price.last_observed_at).toLocaleTimeString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel" aria-labelledby="alerts-title">
          <h2 id="alerts-title" className="panel-title">最近告警</h2>
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
                      <td>{new Date(alert.triggered_at).toLocaleTimeString()}</td>
                      <td>{getInstrumentName(alert.instrument_id)}</td>
                      <td>{alert.alert_kind}</td>
                      <td className="price-cell">{alert.price}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel" aria-labelledby="errors-title">
          <h2 id="errors-title" className="panel-title">数据源错误</h2>
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
                      <td>{new Date(error.last_observed_at).toLocaleTimeString()}</td>
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
