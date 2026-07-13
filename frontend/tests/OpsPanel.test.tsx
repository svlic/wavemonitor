import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OpsPanel } from "../src/pages/ops/OpsPanel";
import { apiClient } from "../src/api/client";

vi.mock("../src/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/client")>();
  return {
    ...actual,
    apiClient: {
      getRuntime: vi.fn(),
      getSourceErrors: vi.fn(),
      getRecentAlerts: vi.fn(),
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

describe("OpsPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows empty recent alerts and source errors on diagnostics page", async () => {
    vi.mocked(apiClient.getRuntime).mockResolvedValue(emptyRuntime);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    render(<OpsPanel />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "最近告警" })).toBeInTheDocument();
      expect(screen.getByText("暂无最近告警。")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "测试告警" })).toBeInTheDocument();
      expect(screen.getByText("暂无数据源错误。")).toBeInTheDocument();
    });
  });

  it("disables test-send when Telegram is not ready", async () => {
    vi.mocked(apiClient.getRuntime).mockResolvedValue(emptyRuntime);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    render(<OpsPanel />);

    await waitFor(() => {
      expect(screen.getByText(/尚未配置/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "发送测试告警" })).not.toBeInTheDocument();
    });
  });

  it("handles successful test-send", async () => {
    vi.mocked(apiClient.getRuntime).mockResolvedValue({
      ...emptyRuntime,
      telegram_ready: true,
    });
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);
    vi.mocked(apiClient.testTelegram).mockResolvedValue({
      sent: true,
      telegram_ready: true,
      detail: "Test message sent",
    });

    render(<OpsPanel />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "发送测试告警" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "发送测试告警" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("测试消息已发送。");
    });
  });

  it("renders source errors when present", async () => {
    vi.mocked(apiClient.getRuntime).mockResolvedValue(emptyRuntime);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);
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

    render(<OpsPanel />);

    await waitFor(() => {
      expect(screen.getByText("Connection timed out")).toBeInTheDocument();
      expect(screen.getByText("2026/06/30 18:00:00 UTC+8")).toBeInTheDocument();
    });
  });

  it("formats alert times in UTC+8 and prices with two decimal places", async () => {
    vi.mocked(apiClient.getRuntime).mockResolvedValue(emptyRuntime);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([
      {
        id: 1,
        instrument_id: 1,
        source_mapping_id: 1,
        alert_kind: "near_support",
        price: "95000.5",
        message: "Bitcoin is near support",
        triggered_at: "2026-06-30T12:00:00Z",
      },
    ]);

    render(<OpsPanel />);

    await waitFor(() => {
      expect(screen.getByText("2026/06/30 20:00:00 UTC+8")).toBeInTheDocument();
      expect(screen.getByText("95000.50")).toBeInTheDocument();
    });
  });
});