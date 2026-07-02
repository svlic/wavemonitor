const PROVIDER_LABELS: Record<string, string> = {
  yfinance: "Yahoo Finance",
  binance: "Binance",
  hyperliquid: "Hyperliquid",
};

const MARKET_TYPE_LABELS: Record<string, string> = {
  equity: "股票",
  usd_m_futures: "USD-M 合约",
  coin_m_futures: "COIN-M 合约",
  perpetual: "永续合约",
};

const ALERT_KIND_LABELS: Record<string, string> = {
  near_support: "接近支撑",
  risk_reward: "风险回报",
  resistance_breakout: "突破阻力",
};

export function formatProviderLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

export function formatMarketTypeLabel(marketType: string): string {
  return MARKET_TYPE_LABELS[marketType] ?? marketType;
}

export function formatSourceLabel(provider: string, marketType: string, symbol: string): string {
  return `${formatProviderLabel(provider)} · ${formatMarketTypeLabel(marketType)} · ${symbol}`;
}

export function formatAlertKindLabel(kind: string): string {
  return ALERT_KIND_LABELS[kind] ?? kind;
}

export const DISPLAY_TIME_ZONE = "Asia/Shanghai";

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("zh-CN", {
    timeZone: DISPLAY_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}