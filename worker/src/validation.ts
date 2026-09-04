import { z } from "zod";
import { decimal, fixed } from "./rules";
import type { MarketType, Provider } from "./types";

const allowedPairs: Record<string, true> = {
  "yfinance:equity": true,
  "binance:usd_m_futures": true,
  "binance:coin_m_futures": true,
  "hyperliquid:perpetual": true,
};
const decimalString = z.union([z.string(), z.number().int()]).transform(String).refine((value) => { try { decimal(value); return true; } catch { return false; } }, "Invalid decimal value");
const optionalDecimal = z.union([decimalString, z.null()]).optional().transform((value) => value == null ? null : fixed(value));
const sourceSchema = z.object({ provider: z.enum(["yfinance", "binance", "hyperliquid"]), market_type: z.enum(["equity", "usd_m_futures", "coin_m_futures", "perpetual"]), symbol: z.string().trim().min(1).max(80), enabled: z.boolean().default(true) }).superRefine((source, ctx) => { if (!allowedPairs[`${source.provider}:${source.market_type}`]) ctx.addIssue({ code: "custom", message: `market_type '${source.market_type}' is not supported for provider '${source.provider}'` }); });

export const instrumentSchema = z.object({
  name: z.string().trim().min(1).max(120), enabled: z.boolean().default(true), alert_mode: z.enum(["static", "fixed_drawdown"]).default("static"), supports: z.array(decimalString).default([]), resistances: z.array(decimalString).default([]), high_water: optionalDecimal, fixed_drawdown: optionalDecimal, near_support_threshold: optionalDecimal, risk_reward_threshold: optionalDecimal, source_mappings: z.array(sourceSchema).min(1),
}).superRefine((data, ctx) => {
  const supports = data.supports.map(decimal); const resistances = data.resistances.map(decimal);
  const issue = (message: string) => ctx.addIssue({ code: "custom", message });
  if (data.alert_mode === "static") {
    if (data.high_water !== null || data.fixed_drawdown !== null) issue("high_water and fixed_drawdown must not be set in static mode");
    if (supports.length === 0 && resistances.length === 0) issue("at least one of support or resistance must be set");
  } else {
    if (supports.length > 0) issue("support is derived");
    if (data.high_water === null || data.fixed_drawdown === null) issue("high_water and fixed_drawdown are required");
    if (resistances.length > 1) issue("fixed_drawdown accepts at most one resistance");
  }
  if ([...supports, ...resistances].some((level) => level.lte(0))) issue("levels must be positive");
  let effectiveSupports = supports;
  if (data.alert_mode === "fixed_drawdown" && data.high_water !== null && data.fixed_drawdown !== null) {
    const derived = decimal(data.high_water).minus(decimal(data.fixed_drawdown));
    if (derived.lte(0)) issue("support must be positive"); else effectiveSupports = [derived];
  }
  if (effectiveSupports.length && resistances.length && effectiveSupports.reduce((a, b) => a.gt(b) ? a : b).gte(resistances.reduce((a, b) => a.lt(b) ? a : b))) issue("support must be less than resistance");
  if (effectiveSupports.length && data.near_support_threshold === null) issue("near_support_threshold is required when support is set");
  if (data.near_support_threshold !== null && (!decimal(data.near_support_threshold).gt(0) || !decimal(data.near_support_threshold).lt(1))) issue("near_support_threshold must be a decimal fraction between 0 and 1");
  if (effectiveSupports.length && resistances.length && data.risk_reward_threshold === null) issue("risk_reward_threshold is required when support and resistance are set");
  if (data.risk_reward_threshold !== null && decimal(data.risk_reward_threshold).lte(0)) issue("risk_reward_threshold must be greater than 0");
  void data.source_mappings;
}).transform((data) => {
  const supports = data.alert_mode === "fixed_drawdown" ? [fixed(decimal(data.high_water!).minus(decimal(data.fixed_drawdown!)))] : data.supports.map(fixed);
  return { ...data, supports, resistances: data.resistances.map(fixed), source_mappings: data.source_mappings.map((source) => ({ ...source, symbol: normalizeSymbol(source.symbol) })) };
});

export function normalizeSymbol(value: string): string { const trimmed = value.trim(); if (!trimmed.includes(":")) return trimmed.toUpperCase(); const [prefix, symbol] = trimmed.split(":", 2) as [string, string]; return `${prefix.toLowerCase()}:${symbol.toUpperCase()}`; }
export type InstrumentInput = z.infer<typeof instrumentSchema>;
export const enabledPatchSchema = z.object({ enabled: z.boolean() }).strict();
export const authSchema = z.object({ password: z.string().min(1) });
const telegramFields = {
  telegram_bot_token: z.string().trim().max(256).optional().default(""),
  telegram_chat_id: z.string().trim().max(128).optional().default(""),
};

function requireTelegramPair(
  data: { telegram_bot_token: string; telegram_chat_id: string },
  ctx: z.RefinementCtx,
): void {
  if (Boolean(data.telegram_bot_token) !== Boolean(data.telegram_chat_id)) {
    ctx.addIssue({ code: "custom", message: "Telegram Bot Token and Chat ID must be set together" });
  }
}

export const setupSchema = z.object({
  password: z.string().min(8).max(256),
  ...telegramFields,
}).superRefine(requireTelegramPair);

export const settingsSchema = z.object({
  new_password: z.string().max(256).optional().default("").refine(
    (value) => value.length === 0 || value.length >= 8,
    "New password must contain at least 8 characters",
  ),
  telegram_enabled: z.boolean(),
  ...telegramFields,
}).superRefine((data, ctx) => {
  if (data.telegram_enabled) requireTelegramPair(data, ctx);
});
export function isProvider(value: string): value is Provider { return ["yfinance", "binance", "hyperliquid"].includes(value); }
export function isMarketType(value: string): value is MarketType { return ["equity", "usd_m_futures", "coin_m_futures", "perpetual"].includes(value); }
