import { marketTypeLabel } from "./marketTypes";

const PROVIDER_LABELS: Record<string, string> = {
  yfinance: "Yahoo Finance",
  binance: "Binance",
  hyperliquid: "Hyperliquid",
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
  return marketTypeLabel(marketType);
}

export function formatSourceLabel(provider: string, marketType: string, symbol: string): string {
  return `${formatProviderLabel(provider)} · ${formatMarketTypeLabel(marketType)} · ${symbol}`;
}

export function formatAlertKindLabel(kind: string): string {
  return ALERT_KIND_LABELS[kind] ?? kind;
}

export const DISPLAY_TIME_ZONE = "Asia/Shanghai";

export function formatDecimal(value: string, fractionDigits = 2): string {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return value;
  }
  return numericValue.toFixed(fractionDigits);
}

export function formatOptionalLevel(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "未设置";
  }
  return formatDecimal(value);
}

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