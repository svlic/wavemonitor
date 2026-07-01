import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

vi.mock("../src/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/client")>();
  return {
    ...actual,
      apiClient: {
      getAuthSession: vi.fn(),
      login: vi.fn(),
      logout: vi.fn(),
      getRuntime: vi.fn(),
      getLatestPrices: vi.fn(),
      getRecentAlerts: vi.fn(),
      getSourceErrors: vi.fn(),
      getInstruments: vi.fn(),
      testTelegram: vi.fn(),
    },
  };
});

import { apiClient } from "../src/api/client";

describe("App shell", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows a recoverable API error when runtime loading fails", async () => {
    // Given: the backend runtime endpoint rejects the request.
    vi.mocked(apiClient.getAuthSession).mockResolvedValue({ authenticated: true, auth_enabled: true });
    vi.mocked(apiClient.getRuntime).mockRejectedValue(new Error("Network error"));
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    // When: the frontend shell renders.
    render(<App />);

    // Then: the user sees the app shell and a recoverable error state.
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "仪表盘" })).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("发生未知错误。");
    });
  });

  it("shows runtime status when loading succeeds", async () => {
    // Given: the backend runtime endpoint returns success.
    vi.mocked(apiClient.getAuthSession).mockResolvedValue({ authenticated: true, auth_enabled: true });
    const mockData = {
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
    vi.mocked(apiClient.getRuntime).mockResolvedValue(mockData);
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    // When: the frontend shell renders.
    render(<App />);

    // Then: the user sees the app shell and the runtime status.
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "仪表盘" })).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText("系统状态")).toBeInTheDocument();
      expect(screen.getByText("Telegram 测试")).toBeInTheDocument();
    });
  });

  it("shows the Chinese password gate before an authenticated session", async () => {
    // Given: web password auth is enabled and the browser has no session.
    vi.mocked(apiClient.getAuthSession).mockResolvedValue({ authenticated: false, auth_enabled: true });

    // When: the frontend shell renders.
    render(<App />);

    // Then: the user sees the Chinese password screen instead of protected data.
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "访问验证" })).toBeInTheDocument();
    });
    expect(screen.getByLabelText("访问密码")).toBeInTheDocument();
  });

  it("logs in and reveals the Chinese dashboard", async () => {
    // Given: auth is enabled and the shared password will be accepted.
    vi.mocked(apiClient.getAuthSession).mockResolvedValue({ authenticated: false, auth_enabled: true });
    vi.mocked(apiClient.login).mockResolvedValue({ authenticated: true, auth_enabled: true });
    vi.mocked(apiClient.getRuntime).mockResolvedValue({
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
    });
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    // When: the password form is submitted.
    render(<App />);
    fireEvent.change(await screen.findByLabelText("访问密码"), { target: { value: "open-sesame" } });
    fireEvent.click(screen.getByRole("button", { name: "进入" }));

    // Then: authenticated users see the Chinese app shell.
    await waitFor(() => {
      expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "仪表盘" })).toBeInTheDocument();
    expect(screen.getByText("标的管理")).toBeInTheDocument();
  });
});
