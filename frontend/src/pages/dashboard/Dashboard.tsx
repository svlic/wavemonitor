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
          setErrorMessage("An unexpected error occurred.");
        }
      }
    }

    void loadData();

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
        setTestMessage("Test message sent successfully.");
      } else {
        setTestStatus("error");
        setTestMessage(response.detail || "Failed to send test message.");
      }
    } catch (error) {
      setTestStatus("error");
      if (error instanceof ApiError) {
        setTestMessage(error.message);
      } else {
        setTestMessage("An unexpected error occurred.");
      }
    }
  };

  if (state === "loading") {
    return (
      <section className="panel" aria-labelledby="dashboard-title">
        <h1 id="dashboard-title">Dashboard</h1>
        <div role="status" aria-live="polite">Loading dashboard data...</div>
      </section>
    );
  }

  if (state === "error") {
    return (
      <section className="panel" aria-labelledby="dashboard-title">
        <h1 id="dashboard-title">Dashboard</h1>
        <div className="error-banner" role="alert">
          <p className="error-text">{errorMessage ?? "Failed to load dashboard."}</p>
        </div>
      </section>
    );
  }

  const getInstrumentName = (id: string) => {
    return instruments.find(i => i.id === id)?.name ?? id;
  };

  const getSourceName = (instrumentId: string, sourceId: string) => {
    const instrument = instruments.find(i => i.id === instrumentId);
    if (!instrument) return sourceId;
    const source = instrument.source_mappings?.find(m => m.id === sourceId);
    if (!source) return sourceId;
    return `${source.provider} (${source.market_type} ${source.symbol})`;
  };

  return (
    <div className="dashboard-layout">
      <div className="dashboard-header">
        <h1 id="dashboard-title">Dashboard</h1>
      </div>

      <div className="dashboard-grid">
        <section className="panel" aria-labelledby="status-title">
          <h2 id="status-title" className="panel-title">System Status</h2>
          <ul className="status-list">
            <li>
              <span className="status-label">Scheduler:</span>
              <span className={`status-value ${runtime?.scheduler_ready ? 'ready' : 'not-ready'}`}>
                {runtime?.scheduler_ready ? "Ready" : "Not Ready"}
              </span>
            </li>
            <li>
              <span className="status-label">Providers:</span>
              <span className={`status-value ${runtime?.providers_ready ? 'ready' : 'not-ready'}`}>
                {runtime?.providers_ready ? "Ready" : "Not Ready"}
              </span>
            </li>
            <li>
              <span className="status-label">Telegram:</span>
              <span className={`status-value ${runtime?.telegram_ready ? 'ready' : 'not-ready'}`}>
                {runtime?.telegram_ready ? "Ready" : "Not Configured"}
              </span>
            </li>
          </ul>

          <div className="telegram-test-section">
            <h3>Telegram Test</h3>
            {!runtime?.telegram_ready ? (
              <p className="muted-text">
                Telegram is not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables to enable alerts.
              </p>
            ) : (
              <div className="test-actions">
                <button 
                  className="button primary" 
                  onClick={() => void handleTestTelegram()}
                  disabled={testStatus === "sending"}
                >
                  {testStatus === "sending" ? "Sending..." : "Send Test Alert"}
                </button>
                {testStatus === "success" && <p className="success-text" role="status">{testMessage}</p>}
                {testStatus === "error" && <p className="error-text" role="alert">{testMessage}</p>}
              </div>
            )}
          </div>
        </section>

        <section className="panel" aria-labelledby="prices-title">
          <h2 id="prices-title" className="panel-title">Latest Prices</h2>
          {prices.length === 0 ? (
            <p className="empty-state">No price data available.</p>
          ) : (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Instrument</th>
                    <th>Source</th>
                    <th>Price</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {prices.map((price, i) => (
                    <tr key={i}>
                      <td>{getInstrumentName(price.instrument_id)}</td>
                      <td>{getSourceName(price.instrument_id, price.source_id)}</td>
                      <td className="price-cell">{price.price}</td>
                      <td>{new Date(price.timestamp).toLocaleTimeString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel" aria-labelledby="alerts-title">
          <h2 id="alerts-title" className="panel-title">Recent Alerts</h2>
          {alerts.length === 0 ? (
            <p className="empty-state">No recent alerts.</p>
          ) : (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Instrument</th>
                    <th>Rule</th>
                    <th>Price</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((alert) => (
                    <tr key={alert.id}>
                      <td>{new Date(alert.created_at).toLocaleTimeString()}</td>
                      <td>{getInstrumentName(alert.instrument_id)}</td>
                      <td>{alert.rule_type}</td>
                      <td className="price-cell">{alert.price}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel" aria-labelledby="errors-title">
          <h2 id="errors-title" className="panel-title">Source Errors</h2>
          {errors.length === 0 ? (
            <p className="empty-state">No recent source errors.</p>
          ) : (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Source ID</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {errors.map((error, i) => (
                    <tr key={i}>
                      <td>{new Date(error.timestamp).toLocaleTimeString()}</td>
                      <td>{error.source_id}</td>
                      <td className="error-cell">{error.message}</td>
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
