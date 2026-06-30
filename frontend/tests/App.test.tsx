import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

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

import { apiClient } from "../src/api/client";

describe("App shell", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows a recoverable API error when runtime loading fails", async () => {
    // Given: the backend runtime endpoint rejects the request.
    vi.mocked(apiClient.getRuntime).mockRejectedValue(new Error("Network error"));
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    // When: the frontend shell renders.
    render(<App />);

    // Then: the user sees the app shell and a recoverable error state.
    expect(screen.getByRole("heading", { name: "WaveMonitor" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("An unexpected error occurred.");
    });
  });

  it("shows runtime status when loading succeeds", async () => {
    // Given: the backend runtime endpoint returns success.
    const mockData = {
      scheduler_ready: true,
      providers_ready: true,
      telegram_ready: false,
    };
    vi.mocked(apiClient.getRuntime).mockResolvedValue(mockData);
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);
    vi.mocked(apiClient.getRecentAlerts).mockResolvedValue([]);
    vi.mocked(apiClient.getSourceErrors).mockResolvedValue([]);
    vi.mocked(apiClient.getInstruments).mockResolvedValue([]);

    // When: the frontend shell renders.
    render(<App />);

    // Then: the user sees the app shell and the runtime status.
    expect(screen.getByRole("heading", { name: "WaveMonitor" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("System Status")).toBeInTheDocument();
      expect(screen.getByText("Telegram Test")).toBeInTheDocument();
    });
  });
});
