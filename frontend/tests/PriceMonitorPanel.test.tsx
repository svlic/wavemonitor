import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { InstrumentWithMappings, LatestPrice } from "../src/api/client";
import { PriceMonitorPanel } from "../src/pages/dashboard/PriceMonitorPanel";

const instruments = [
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
  {
    id: 2,
    name: "Ethereum",
    enabled: true,
    support: "3000",
    resistance: "4000",
    near_support_threshold: "0.01",
    risk_reward_threshold: "2.0",
    source_mappings: [
      {
        id: 2,
        provider: "binance",
        market_type: "usd_m_futures",
        symbol: "ETHUSDT",
        enabled: true,
      },
    ],
  },
  {
    id: 3,
    name: "Apple",
    enabled: true,
    support: "180",
    resistance: "220",
    near_support_threshold: "0.01",
    risk_reward_threshold: "2.0",
    source_mappings: [
      {
        id: 3,
        provider: "yfinance",
        market_type: "spot",
        symbol: "AAPL",
        enabled: true,
      },
    ],
  },
] satisfies readonly InstrumentWithMappings[];

const prices = [
  {
    instrument_id: 2,
    instrument_name: "Ethereum",
    source_mapping_id: 2,
    provider: "binance",
    market_type: "usd_m_futures",
    symbol: "ETHUSDT",
    last_price: "3500.00",
    last_observed_at: "2026-06-30T12:00:00Z",
    last_error: null,
    support_breached: false,
    resistance_broken: true,
  },
  {
    instrument_id: 1,
    instrument_name: "Bitcoin",
    source_mapping_id: 1,
    provider: "binance",
    market_type: "usd_m_futures",
    symbol: "BTCUSDT",
    last_price: "95000.50",
    last_observed_at: "2026-06-30T12:01:00Z",
    last_error: null,
    support_breached: true,
    resistance_broken: false,
  },
  {
    instrument_id: 3,
    instrument_name: "Apple",
    source_mapping_id: 3,
    provider: "yfinance",
    market_type: "spot",
    symbol: "AAPL",
    last_price: "200.00",
    last_observed_at: "2026-06-30T12:02:00Z",
    last_error: null,
    support_breached: false,
    resistance_broken: false,
  },
] satisfies readonly LatestPrice[];

describe("PriceMonitorPanel", () => {
  it("sorts instruments by name", () => {
    render(<PriceMonitorPanel prices={prices} instruments={instruments} />);

    const instrumentNames = document.querySelectorAll(".price-table-row__instrument-name");
    expect(Array.from(instrumentNames, (name) => name.textContent ?? "")).toEqual([
      "Apple",
      "Bitcoin",
      "Ethereum",
    ]);
  });

  it("formats prices and configured levels with two decimal places", () => {
    render(<PriceMonitorPanel prices={prices} instruments={instruments} />);

    expect(screen.getByText("95000.50")).toBeInTheDocument();
    expect(screen.getByText("90000.00")).toBeInTheDocument();
    expect(screen.getByText("100000.00")).toBeInTheDocument();
  });

  it("formats observation times in UTC+8", () => {
    render(<PriceMonitorPanel prices={prices} instruments={instruments} />);

    expect(screen.getByText("2026/06/30 20:01:00 UTC+8")).toBeInTheDocument();
  });

  it("marks historical support breaches and resistance breakouts on affected rows", () => {
    render(<PriceMonitorPanel prices={prices} instruments={instruments} />);

    const bitcoinRow = screen.getByText("Bitcoin").closest("tr");
    const ethereumRow = screen.getByText("Ethereum").closest("tr");
    const appleRow = screen.getByText("Apple").closest("tr");
    expect(bitcoinRow).toHaveTextContent("曾跌破支撑");
    expect(bitcoinRow).not.toHaveTextContent("曾突破阻力");
    expect(ethereumRow).toHaveTextContent("曾突破阻力");
    expect(ethereumRow).not.toHaveTextContent("曾跌破支撑");
    expect(appleRow).not.toHaveTextContent("曾跌破支撑");
    expect(appleRow).not.toHaveTextContent("曾突破阻力");
  });
});
