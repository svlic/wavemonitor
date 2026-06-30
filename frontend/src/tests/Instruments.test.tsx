import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { InstrumentList } from "../pages/instruments/InstrumentList";
import { InstrumentForm } from "../pages/instruments/InstrumentForm";
import { apiClient } from "../api/client";

import type { InstrumentWithMappings } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    apiClient: {
      getInstruments: vi.fn(),
      getInstrument: vi.fn(),
      createInstrument: vi.fn(),
      updateInstrument: vi.fn(),
      deleteInstrument: vi.fn(),
    },
  };
});

const mockInstruments: readonly InstrumentWithMappings[] = [
  {
    id: "1",
    name: "BTC/USD",
    enabled: true,
    support: "60000",
    resistance: "65000",
    near_support_threshold: "0.05",
    risk_reward_threshold: "2.0",
    source_mappings: [
      {
        id: "m1",
        instrument_id: "1",
        provider: "binance",
        market_type: "usd_m_futures",
        symbol: "BTCUSDT",
        enabled: true,
      },
    ],
  },
];

describe("InstrumentList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockImplementation(() => true);
  });

  it("renders loading state initially", () => {
    vi.mocked(apiClient.getInstruments).mockReturnValue(new Promise(() => {}));
    render(<InstrumentList />);
    expect(screen.getByText("Loading instruments...")).toBeInTheDocument();
  });

  it("renders list of instruments", async () => {
    vi.mocked(apiClient.getInstruments).mockResolvedValue(mockInstruments);
    render(<InstrumentList />);
    
    await waitFor(() => {
      expect(screen.getByText("BTC/USD")).toBeInTheDocument();
    });
    expect(screen.getByText("60000")).toBeInTheDocument();
    expect(screen.getByText("65000")).toBeInTheDocument();
  });

  it("handles API error", async () => {
    vi.mocked(apiClient.getInstruments).mockRejectedValue(new Error("API Error"));
    render(<InstrumentList />);
    
    await waitFor(() => {
      expect(screen.getByText("Failed to load instruments. Please try again.")).toBeInTheDocument();
    });
  });

  it("handles delete flow", async () => {
    vi.mocked(apiClient.getInstruments).mockResolvedValue(mockInstruments);
    vi.mocked(apiClient.deleteInstrument).mockResolvedValue(undefined);
    
    render(<InstrumentList />);
    
    await waitFor(() => {
      expect(screen.getByText("BTC/USD")).toBeInTheDocument();
    });

    const deleteButton = screen.getByRole("button", { name: /delete/i });
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(apiClient.deleteInstrument).toHaveBeenCalledWith("1");
    });
  });
});

describe("InstrumentForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("validates support and resistance", async () => {
    render(<InstrumentForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    
    const nameInput = screen.getByLabelText(/^name/i);
    const supportInput = screen.getByLabelText(/^support level/i);
    const resistanceInput = screen.getByLabelText(/^resistance level/i);
    const nearSupportThresholdInput = screen.getByLabelText(/^near support threshold/i);
    const riskRewardThresholdInput = screen.getByLabelText(/^risk reward threshold/i);
    
    fireEvent.change(nameInput, { target: { value: "Test" } });
    fireEvent.change(supportInput, { target: { value: "100" } });
    fireEvent.change(resistanceInput, { target: { value: "50" } }); // Invalid: resistance < support
    fireEvent.change(nearSupportThresholdInput, { target: { value: "0.05" } });
    fireEvent.change(riskRewardThresholdInput, { target: { value: "2.0" } });
    
    const submitButton = screen.getByRole("button", { name: /save/i });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(screen.getByText("Support must be strictly less than resistance")).toBeInTheDocument();
    });
  });

  it("submits valid form", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<InstrumentForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    
    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: "Test" } });
    fireEvent.change(screen.getByLabelText(/^support level/i), { target: { value: "50" } });
    fireEvent.change(screen.getByLabelText(/^resistance level/i), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText(/^near support threshold/i), { target: { value: "0.05" } });
    fireEvent.change(screen.getByLabelText(/^risk reward threshold/i), { target: { value: "2.0" } });
    
    // Add mapping
    fireEvent.click(screen.getByRole("button", { name: /add source/i }));
    
    const providerSelects = screen.getAllByLabelText(/^provider/i);
    if (providerSelects[0]) {
      fireEvent.change(providerSelects[0], { target: { value: "yfinance" } });
    }
    
    const symbolInputs = screen.getAllByLabelText(/^symbol/i);
    if (symbolInputs[0]) {
      fireEvent.change(symbolInputs[0], { target: { value: "TEST" } });
    }
    
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        name: "Test",
        enabled: true,
        support: "50",
        resistance: "100",
        near_support_threshold: "0.05",
        risk_reward_threshold: "2.0",
        source_mappings: [
          {
            provider: "yfinance",
            market_type: "equity",
            symbol: "TEST",
            enabled: true,
          }
        ]
      });
    });
  });
});
