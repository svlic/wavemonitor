export type Provider = "yfinance" | "binance" | "hyperliquid";
export type MarketType = "equity" | "usd_m_futures" | "coin_m_futures" | "perpetual";
export type AlertMode = "static" | "fixed_drawdown";
export type AlertKind = "near_support" | "risk_reward" | "resistance_breakout" | "support_breach";

export interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
  TELEGRAM_BOT_TOKEN?: string;
  TELEGRAM_CHAT_ID?: string;
  WAVEMONITOR_WEB_PASSWORD?: string;
  WAVEMONITOR_SESSION_SECRET?: string;
}

export interface SourceMapping {
  id: number;
  instrument_id: number;
  provider: Provider;
  market_type: MarketType;
  symbol: string;
  enabled: number;
}

export interface Instrument {
  id: number;
  name: string;
  enabled: number;
  alert_mode: AlertMode;
  supports: string;
  resistances: string;
  high_water: string | null;
  fixed_drawdown: string | null;
  near_support_threshold: string | null;
  risk_reward_threshold: string | null;
  created_at: string | null;
  updated_at: string | null;
  rule_cycle_started_at: string;
}

export interface EnabledSource extends SourceMapping {
  instrument_name: string;
  alert_mode: AlertMode;
  supports: string;
  resistances: string;
  high_water: string | null;
  fixed_drawdown: string | null;
  near_support_threshold: string | null;
  risk_reward_threshold: string | null;
  rule_cycle_started_at: string;
}

export interface RuleState {
  last_price: string | null;
  near_support_active: number;
  risk_reward_active: number;
  above_resistance_active: number;
  support_breach_active: number;
  near_support_last_alert_at: string | null;
  risk_reward_last_alert_at: string | null;
  breakout_last_alert_at: string | null;
  support_breach_last_alert_at: string | null;
  last_invalid_state: string | null;
}

export interface AlertDecision {
  kind: AlertKind;
  price: string;
  support: string;
  resistance: string;
  threshold: string | null;
  metric: string;
  triggered_at: string;
  message: string;
}
