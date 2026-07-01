import { describe, expect, it } from "vitest";
import {
  defaultMarketTypeForProvider,
  marketTypeLabel,
  marketTypesForProvider,
} from "../utils/marketTypes";

describe("marketTypesForProvider", () => {
  it("exposes only equity for yfinance", () => {
    expect(marketTypesForProvider("yfinance")).toEqual(["equity"]);
  });

  it("exposes futures types for binance", () => {
    expect(marketTypesForProvider("binance")).toEqual(["usd_m_futures", "coin_m_futures"]);
  });

  it("exposes perpetual for hyperliquid", () => {
    expect(marketTypesForProvider("hyperliquid")).toEqual(["perpetual"]);
  });
});

describe("defaultMarketTypeForProvider", () => {
  it("matches backend adapter defaults", () => {
    expect(defaultMarketTypeForProvider("yfinance")).toBe("equity");
    expect(defaultMarketTypeForProvider("binance")).toBe("usd_m_futures");
    expect(defaultMarketTypeForProvider("hyperliquid")).toBe("perpetual");
  });
});

describe("marketTypeLabel", () => {
  it("returns Chinese labels for known market types", () => {
    expect(marketTypeLabel("equity")).toBe("股票");
    expect(marketTypeLabel("perpetual")).toBe("永续合约");
  });
});