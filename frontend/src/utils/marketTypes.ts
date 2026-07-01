export type ProviderId = "yfinance" | "binance" | "hyperliquid";

export type MarketTypeId = "equity" | "usd_m_futures" | "coin_m_futures" | "perpetual";

const MARKET_TYPE_LABELS: Record<MarketTypeId, string> = {
  equity: "股票",
  usd_m_futures: "USD-M 合约",
  coin_m_futures: "COIN-M 合约",
  perpetual: "永续合约",
};

const MARKET_TYPES_BY_PROVIDER: Record<ProviderId, readonly MarketTypeId[]> = {
  yfinance: ["equity"],
  binance: ["usd_m_futures", "coin_m_futures"],
  hyperliquid: ["perpetual"],
};

const DEFAULT_MARKET_TYPE: Record<ProviderId, MarketTypeId> = {
  yfinance: "equity",
  binance: "usd_m_futures",
  hyperliquid: "perpetual",
};

export function marketTypesForProvider(provider: string): readonly MarketTypeId[] {
  if (provider === "yfinance" || provider === "binance" || provider === "hyperliquid") {
    return MARKET_TYPES_BY_PROVIDER[provider];
  }
  return MARKET_TYPES_BY_PROVIDER.yfinance;
}

export function defaultMarketTypeForProvider(provider: string): MarketTypeId {
  if (provider === "yfinance" || provider === "binance" || provider === "hyperliquid") {
    return DEFAULT_MARKET_TYPE[provider];
  }
  return "equity";
}

export function marketTypeLabel(marketType: string): string {
  if (marketType in MARKET_TYPE_LABELS) {
    return MARKET_TYPE_LABELS[marketType as MarketTypeId];
  }
  return marketType;
}