import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "../src/pages/dashboard/Dashboard";
import { apiClient } from "../src/api/client";
import type { InstrumentWithMappings } from "../src/api/client";

vi.mock("../src/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/client")>();
  return {
    ...actual,
    apiClient: {
      getRuntime: vi.fn(),
      getLatestPrices: vi.fn(),
      getRecentAlerts: vi.fn(),
      getSourceErrors: vi.fn(),
      getInstruments: vi.fn(),
      testTelegram: vi.fn(),
    },
  };
});

const emptyRuntime = {
  scheduler_ready: true,
  providers_ready: true,
  telegram_ready: false,
  enabled_sources: 0,
  polled_sources: 0,
  observations_written: 0,
  source_errors: 0,
  alert_events_created: 0,
  telegram_deliveries_attempted: 0,
  last_tick_started_at: null,
  last_tick_finished_at: null,
};

describe("Dashboard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows loading state initially", () => {
    vi.mocked(apiClient.getRuntime).mockImplementation(() => new Promise(() => {}));
    vi.mocked(apiClient.getLatestPrices).mockImplementation(() => new Promise(() => {}));
    vi.mocked(apiClient.getRecentAlerts).mockImplementation(() => new Promise(() => {}));
    vi.mocked(apiClient.getSourceErrors).mockImplementation(() => new Promise(() => {}));
    vi.mocked(apiClient.getInstruments).mockImplementation(() => new Promise(() => {}));

    render(<Dashboard />);

    expect(screen.getByRole("status")).toHaveTextContent("正在加载仪表盘数据...");
  });

  it("shows error state when API fails", async () => {
    vi.mocked(apiClient.getRuntime).mockRejectedValue(new Error("Network error"));
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("发生未知错误。");
    });
  });

  it("shows empty state when no data exists", async () => {
    vi.mocked(apiClient.getRuntime).mockResolvedValue(emptyRuntime);
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText("暂无价格数据。")).toBeInTheDocument();
      expect(screen.getByText("暂无最近告警。")).toBeInTheDocument();
      expect(screen.getByText("暂无数据源错误。")).toBeInTheDocument();
    });
  });

  it("renders latest prices, alerts, and errors when data exists", async () => {
    vi.mocked(apiClient.getRuntime).mockResolvedValue({
      ...emptyRuntime,
      telegram_ready: true,
    });
    vi.mocked(apiClient.getInstruments).mockResolvedValue([
      {
        id: 1,
        name: "Bitcoin",
        enabled: true,
        support: "90000",
        resistance: "100000",
        near_support_threshold: "0.01",
        risk_reward_threshold: "2.0",
        source_mappings: [
          {
            id: 1,
            provider: "binance",
            market_type: "usd_m_futures",
            symbol: "BTCUSDT",
            enabled: true,
          },
        ],
      },
    ] satisfies readonly InstrumentWithMappings[]);
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([
      {
        instrument_id: 1,
        instrument_name: "Bitcoin",
        source_mapping_id: 1,
        provider: "binance",
        market_type: "usd_m_futures",
        symbol: "BTCUSDT",
        last_price: "95000.50",
        last_observed_at: "2026-06-30T12:00:00Z",
        last_error: null,
      },
    ]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([
      {
        id: 1,
        instrument_id: 1,
        source_mapping_id: 1,
        alert_kind: "near_support",
        price: "90500.00",
        message: "Near support",
        triggered_at: "2026-06-30T11:00:00Z",
      },
    ]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([
      {
        instrument_id: 1,
        instrument_name: "Bitcoin",
        source_mapping_id: 1,
        provider: "binance",
        market_type: "usd_m_futures",
        symbol: "BTCUSDT",
        last_observed_at: "2026-06-30T10:00:00Z",
        last_error: "Connection timed out",
      },
    ]);

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getAllByText("Bitcoin").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Binance · USD-M 合约 · BTCUSDT").length).toBeGreaterThan(0);
      expect(screen.getByText("95000.50")).toBeInTheDocument();
      expect(screen.getByText("接近支撑")).toBeInTheDocument();
      expect(screen.getByText("90500.00")).toBeInTheDocument();
      expect(screen.getByText("Connection timed out")).toBeInTheDocument();
    });
  });

  it("disables test-send and explains required env vars when Telegram is not ready", async () => {
    vi.mocked(apiClient.getRuntime).mockResolvedValue(emptyRuntime);
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText(/Telegram 尚未配置/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "发送测试告警" })).not.toBeInTheDocument();
    });
  });

  it("handles successful test-send", async () => {
    vi.mocked(apiClient.getRuntime).mockResolvedValue({
      ...emptyRuntime,
      telegram_ready: true,
    });
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);
    vi.mocked(apiClient.testTelegram).mockResolvedValue({
      sent: true,
      telegram_ready: true,
      detail: "Test message sent",
    });

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "发送测试告警" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "发送测试告警" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("测试消息已发送。");
    });
  });

  it("handles failed test-send", async () => {
    vi.mocked(apiClient.getRuntime).mockResolvedValue({
      ...emptyRuntime,
      telegram_ready: true,
    });
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);
    vi.mocked(apiClient.testTelegram).mockResolvedValue({
      sent: false,
      telegram_ready: true,
      detail: "Invalid chat ID",
    });

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "发送测试告警" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "发送测试告警" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Invalid chat ID");
    });
  });
});