import { act } from "react";
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
      patchInstrumentEnabled: vi.fn(),
      querySymbols: vi.fn(),
    },
  };
});

const mockInstruments: readonly InstrumentWithMappings[] = [
  {
    id: 1,
    name: "BTC/USD",
    enabled: true,
    support: "60000",
    resistance: "65000",
    near_support_threshold: "0.05",
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
];

describe("InstrumentList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading state initially", () => {
    vi.mocked(apiClient.getInstruments).mockReturnValue(new Promise(() => {}));
    render(<InstrumentList />);
    expect(screen.getByText("正在加载标的...")).toBeInTheDocument();
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
      expect(screen.getByText("标的列表加载失败，请重试。")).toBeInTheDocument();
    });
  });

  it("handles delete flow", async () => {
    vi.mocked(apiClient.getInstruments).mockResolvedValue(mockInstruments);
    vi.mocked(apiClient.deleteInstrument).mockResolvedValue(undefined);
    
    render(<InstrumentList />);
    
    await waitFor(() => {
      expect(screen.getByText("BTC/USD")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    fireEvent.click(screen.getByRole("button", { name: "确认" }));

    await waitFor(() => {
      expect(apiClient.deleteInstrument).toHaveBeenCalledWith(1);
    });
  });

  it("pauses and resumes monitoring from the list", async () => {
    vi.mocked(apiClient.getInstruments).mockResolvedValue(mockInstruments);
    vi.mocked(apiClient.patchInstrumentEnabled).mockResolvedValue({
      ...mockInstruments[0],
      enabled: false,
    });

    render(<InstrumentList />);

    await waitFor(() => {
      expect(screen.getByText("BTC/USD")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "暂停" }));

    await waitFor(() => {
      expect(apiClient.patchInstrumentEnabled).toHaveBeenCalledWith(1, false);
    });
    expect(screen.getByText("已暂停")).toBeInTheDocument();

    vi.mocked(apiClient.patchInstrumentEnabled).mockResolvedValue(mockInstruments[0]);
    fireEvent.click(screen.getByRole("button", { name: "恢复" }));

    await waitFor(() => {
      expect(apiClient.patchInstrumentEnabled).toHaveBeenCalledWith(1, true);
    });
    expect(screen.getByText("监控中")).toBeInTheDocument();
  });
});

describe("InstrumentForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.querySymbols).mockResolvedValue([]);
  });

  it("validates support and resistance", async () => {
    render(<InstrumentForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    
    const nameInput = screen.getByLabelText("名称");
    const supportInput = screen.getByLabelText("支撑位");
    const resistanceInput = screen.getByLabelText("阻力位");
    const nearSupportThresholdInput = screen.getByLabelText(/^接近支撑阈值/);
    const riskRewardThresholdInput = screen.getByLabelText(/^风险回报阈值/);
    
    fireEvent.change(nameInput, { target: { value: "Test" } });
    fireEvent.change(supportInput, { target: { value: "100" } });
    fireEvent.change(resistanceInput, { target: { value: "50" } }); // Invalid: resistance < support
    fireEvent.change(nearSupportThresholdInput, { target: { value: "0.05" } });
    fireEvent.change(riskRewardThresholdInput, { target: { value: "2.0" } });
    
    const submitButton = screen.getByRole("button", { name: "保存标的" });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(screen.getByText("支撑位必须严格小于阻力位")).toBeInTheDocument();
    });
  });

  it("queries realtime symbol options and applies the selected option", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    vi.mocked(apiClient.querySymbols)
      .mockResolvedValueOnce([
        { symbol: "BTCUSDT", label: "BTCUSDT", provider: "binance", market_type: "usd_m_futures" },
      ])
      .mockResolvedValue([]);
    render(<InstrumentForm onSubmit={onSubmit} onCancel={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "添加来源" }));
    fireEvent.change(screen.getByLabelText("数据源"), { target: { value: "binance" } });
    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "btc" } });

    await waitFor(() => {
      expect(apiClient.querySymbols).toHaveBeenCalledWith("binance", "usd_m_futures", "btc", expect.any(AbortSignal));
    });
    const option = await screen.findByRole("option", { name: "BTCUSDT" });
    await act(async () => {
      fireEvent.pointerDown(option);
    });

    await waitFor(() => {
      expect(screen.getByLabelText("Symbol")).toHaveValue("BTCUSDT");
    });
    await waitFor(() => {
      expect(screen.queryByRole("listbox", { name: "Symbol 候选项" })).not.toBeInTheDocument();
    });
  });

  it("applies a yfinance symbol option and closes the dropdown", async () => {
    vi.mocked(apiClient.querySymbols)
      .mockResolvedValueOnce([
        { symbol: "AAPL", label: "AAPL — Apple Inc.", provider: "yfinance", market_type: "equity" },
      ])
      .mockResolvedValue([]);
    render(<InstrumentForm onSubmit={vi.fn()} onCancel={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "添加来源" }));
    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "app" } });

    await waitFor(() => {
      expect(apiClient.querySymbols).toHaveBeenCalledWith("yfinance", "equity", "app", expect.any(AbortSignal));
    });
    const option = await screen.findByRole("option", { name: "AAPL — Apple Inc." });
    await act(async () => {
      fireEvent.mouseDown(option);
    });

    await waitFor(() => {
      expect(screen.getByLabelText("Symbol")).toHaveValue("AAPL");
    });
    await waitFor(() => {
      expect(screen.queryByRole("listbox", { name: "Symbol 候选项" })).not.toBeInTheDocument();
    });
  });

  it("limits market type options to the selected provider", async () => {
    render(<InstrumentForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "添加来源" }));

    expect(screen.getByLabelText("市场类型")).toHaveValue("equity");
    expect(screen.getByRole("option", { name: "股票" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "USD-M 合约" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("数据源"), { target: { value: "binance" } });
    await waitFor(() => {
      expect(screen.getByLabelText("市场类型")).toHaveValue("usd_m_futures");
    });
    expect(screen.getByRole("option", { name: "USD-M 合约" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "COIN-M 合约" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "股票" })).not.toBeInTheDocument();
  });

  it("submits valid form", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<InstrumentForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    
    fireEvent.change(screen.getByLabelText("名称"), { target: { value: "Test" } });
    fireEvent.change(screen.getByLabelText("支撑位"), { target: { value: "50" } });
    fireEvent.change(screen.getByLabelText("阻力位"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText(/^接近支撑阈值/), { target: { value: "0.05" } });
    fireEvent.change(screen.getByLabelText(/^风险回报阈值/), { target: { value: "2.0" } });
    
    // Add mapping
    fireEvent.click(screen.getByRole("button", { name: "添加来源" }));
    
    const providerSelects = screen.getAllByLabelText("数据源");
    if (providerSelects[0]) {
      fireEvent.change(providerSelects[0], { target: { value: "yfinance" } });
    }
    
    const symbolInputs = screen.getAllByLabelText(/^symbol/i);
    if (symbolInputs[0]) {
      fireEvent.change(symbolInputs[0], { target: { value: "TEST" } });
    }
    
    fireEvent.click(screen.getByRole("button", { name: "保存标的" }));
    
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
