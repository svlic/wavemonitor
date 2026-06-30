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

describe("Dashboard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows loading state initially", () => {
    // Given: API calls are pending
    vi.mocked(apiClient.getRuntime).mockImplementation(() => new Promise(() => {}));
    vi.mocked(apiClient.getLatestPrices).mockImplementation(() => new Promise(() => {}));
    vi.mocked(apiClient.getRecentAlerts).mockImplementation(() => new Promise(() => {}));
    vi.mocked(apiClient.getSourceErrors).mockImplementation(() => new Promise(() => {}));
    vi.mocked(apiClient.getInstruments).mockImplementation(() => new Promise(() => {}));

    // When: Dashboard renders
    render(<Dashboard />);

    // Then: Loading state is shown
    expect(screen.getByRole("status")).toHaveTextContent("Loading dashboard data...");
  });

  it("shows error state when API fails", async () => {
    // Given: API call fails
    vi.mocked(apiClient.getRuntime).mockRejectedValue(new Error("Network error"));
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    // When: Dashboard renders
    render(<Dashboard />);

    // Then: Error state is shown
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("An unexpected error occurred.");
    });
  });

  it("shows empty state when no data exists", async () => {
    // Given: API returns empty data
    vi.mocked(apiClient.getRuntime).mockResolvedValue({
      scheduler_ready: true,
      providers_ready: true,
      telegram_ready: false,
    });
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    // When: Dashboard renders
    render(<Dashboard />);

    // Then: Empty states are shown
    await waitFor(() => {
      expect(screen.getByText("No price data available.")).toBeInTheDocument();
      expect(screen.getByText("No recent alerts.")).toBeInTheDocument();
      expect(screen.getByText("No recent source errors.")).toBeInTheDocument();
    });
  });

  it("renders latest prices, alerts, and errors when data exists", async () => {
    // Given: API returns data
    vi.mocked(apiClient.getRuntime).mockResolvedValue({
      scheduler_ready: true,
      providers_ready: true,
      telegram_ready: true,
    });
    vi.mocked(apiClient.getInstruments).mockResolvedValue([
      {
        id: "inst-1",
        name: "Bitcoin",
        enabled: true,
        support: "90000",
        resistance: "100000",
        near_support_threshold: "0.01",
        risk_reward_threshold: "2.0",
        source_mappings: [
          { id: "src-1", instrument_id: "inst-1", provider: "binance", market_type: "usd_m_futures", symbol: "BTCUSDT", enabled: true }
        ]
      }
    ] satisfies readonly InstrumentWithMappings[]);
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([
      { instrument_id: "inst-1", source_id: "src-1", price: "95000.50", timestamp: "2026-06-30T12:00:00Z" }
    ]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([
      { id: "alert-1", instrument_id: "inst-1", source_id: "src-1", price: "90500.00", rule_type: "near_support", created_at: "2026-06-30T11:00:00Z" }
    ]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([
      { source_id: "src-1", error_type: "timeout", message: "Connection timed out", timestamp: "2026-06-30T10:00:00Z" }
    ]);

    // When: Dashboard renders
    render(<Dashboard />);

    // Then: Data is rendered correctly
    await waitFor(() => {
      // Prices
      expect(screen.getAllByText("Bitcoin").length).toBeGreaterThan(0);
      expect(screen.getByText("binance (usd_m_futures BTCUSDT)")).toBeInTheDocument();
      expect(screen.getByText("95000.50")).toBeInTheDocument();
      
      // Alerts
      expect(screen.getByText("near_support")).toBeInTheDocument();
      expect(screen.getByText("90500.00")).toBeInTheDocument();

      // Errors
      expect(screen.getByText("Connection timed out")).toBeInTheDocument();
    });
  });

  it("disables test-send and explains required env vars when Telegram is not ready", async () => {
    // Given: Telegram is not ready
    vi.mocked(apiClient.getRuntime).mockResolvedValue({
      scheduler_ready: true,
      providers_ready: true,
      telegram_ready: false,
    });
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    // When: Dashboard renders
    render(<Dashboard />);

    // Then: Test button is not shown, explanation is shown
    await waitFor(() => {
      expect(screen.getByText(/Telegram is not configured/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Send Test Alert" })).not.toBeInTheDocument();
    });
  });

  it("handles successful test-send", async () => {
    // Given: Telegram is ready and test succeeds
    vi.mocked(apiClient.getRuntime).mockResolvedValue({
      scheduler_ready: true,
      providers_ready: true,
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

    // When: Dashboard renders and user clicks test button
    render(<Dashboard />);
    
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Send Test Alert" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Send Test Alert" }));

    // Then: Success message is shown
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("Test message sent successfully.");
    });
  });

  it("handles failed test-send", async () => {
    // Given: Telegram is ready but test fails
    vi.mocked(apiClient.getRuntime).mockResolvedValue({
      scheduler_ready: true,
      providers_ready: true,
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

    // When: Dashboard renders and user clicks test button
    render(<Dashboard />);
    
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Send Test Alert" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Send Test Alert" }));

    // Then: Error message is shown
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Invalid chat ID");
    });
  });
});
