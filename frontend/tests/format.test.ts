import { afterEach, describe, expect, it, vi } from "vitest";
import { DISPLAY_TIME_ZONE, formatDateTime, formatSourceLabel } from "../src/utils/format";

describe("formatSourceLabel", () => {
  it.each([
    ["yfinance", "equity", "AAPL", "Yahoo Finance · 股票 · AAPL"],
    ["binance", "usd_m_futures", "BTCUSDT", "Binance · USD-M 合约 · BTCUSDT"],
    ["binance", "coin_m_futures", "BTCUSD_PERP", "Binance · COIN-M 合约 · BTCUSD_PERP"],
    ["hyperliquid", "perpetual", "xyz:AAPL", "Hyperliquid · 永续合约 · xyz:AAPL"],
    ["custom", "custom-market", " mixed:Symbol ", "custom · custom-market ·  mixed:Symbol "],
    ["", "", "", " ·  · "],
  ])("preserves source label for %s / %s", (provider, market, symbol, expected) => {
    expect(formatSourceLabel(provider, market, symbol)).toBe(expected);
  });
});

describe("formatDateTime", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("formats UTC instants in Asia/Shanghai (UTC+8)", () => {
    expect(DISPLAY_TIME_ZONE).toBe("Asia/Shanghai");
    expect(formatDateTime("2026-06-30T12:00:00Z")).toBe("2026/06/30 20:00:00 UTC+8");
  });

  it("treats timezone-less API timestamps as UTC when the browser is in UTC+8", () => {
    vi.stubEnv("TZ", "Asia/Shanghai");

    expect(formatDateTime("2026-06-30T12:00:00")).toBe("2026/06/30 20:00:00 UTC+8");
  });

  it("preserves explicit offsets before converting to UTC+8", () => {
    expect(formatDateTime("2026-06-30T12:00:00+02:00")).toBe("2026/06/30 18:00:00 UTC+8");
  });

  it("returns original string when iso is invalid", () => {
    expect(formatDateTime("not-a-date")).toBe("not-a-date");
  });
});
