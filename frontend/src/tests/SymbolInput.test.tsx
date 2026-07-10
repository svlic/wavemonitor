import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client";
import { SymbolInput } from "../pages/instruments/SymbolInput";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    apiClient: {
      querySymbols: vi.fn(),
    },
  };
});

describe("SymbolInput", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.querySymbols).mockResolvedValue([
      {
        symbol: "BTCUSDT",
        label: "BTCUSDT",
        provider: "binance",
        market_type: "usd_m_futures",
      },
    ]);
  });

  it("keeps existing symbol suggestions closed until the input is focused", async () => {
    // Given: an edit form symbol already has a value.
    render(
      <SymbolInput
        id="symbol-0"
        provider="binance"
        marketType="usd_m_futures"
        value="BTCUSDT"
        onChange={vi.fn()}
      />,
    );

    const input = screen.getByRole("combobox", { name: "" });

    // Then: mounting the existing value neither searches nor opens suggestions.
    expect(apiClient.querySymbols).not.toHaveBeenCalled();
    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("listbox", { name: "Symbol 候选项" })).not.toBeInTheDocument();

    // When: the user explicitly focuses the symbol input.
    fireEvent.focus(input);

    // Then: suggestions are queried and shown for the existing value.
    await waitFor(() => {
      expect(apiClient.querySymbols).toHaveBeenCalledWith(
        "binance",
        "usd_m_futures",
        "BTCUSDT",
        expect.any(AbortSignal),
      );
    });
    expect(await screen.findByRole("listbox", { name: "Symbol 候选项" })).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-expanded", "true");
  });
});
