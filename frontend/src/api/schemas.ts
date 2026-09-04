import { z } from "zod";

const isoDateTime = z.union([z.string(), z.number()]).transform((v) =>
  typeof v === "number" ? new Date(v).toISOString() : v,
);

export const RuntimeResponseSchema = z.object({
  scheduler_ready: z.boolean(),
  providers_ready: z.boolean(),
  telegram_ready: z.boolean(),
  enabled_sources: z.number(),
  polled_sources: z.number(),
  observations_written: z.number(),
  source_errors: z.number(),
  alert_events_created: z.number(),
  telegram_deliveries_attempted: z.number(),
  last_tick_started_at: z.string().nullable(),
  last_tick_finished_at: z.string().nullable(),
});

export type RuntimeResponse = z.infer<typeof RuntimeResponseSchema>;

export const AuthStatusResponseSchema = z.object({
  authenticated: z.boolean(),
  auth_enabled: z.boolean(),
  setup_required: z.boolean().optional(),
  configuration_available: z.boolean().optional(),
});

export type AuthStatusResponse = z.infer<typeof AuthStatusResponseSchema>;
export const AppSettingsResponseSchema = z.object({
  telegram_enabled: z.boolean(),
  password_configured: z.boolean(),
  managed_in_gui: z.boolean(),
});

export type AppSettingsResponse = z.infer<typeof AppSettingsResponseSchema>;

export type SetupRequest = {
  password: string;
  telegram_bot_token: string;
  telegram_chat_id: string;
};

export type UpdateSettingsRequest = {
  new_password: string;
  telegram_enabled: boolean;
  telegram_bot_token: string;
  telegram_chat_id: string;
};

export const TelegramTestResponseSchema = z.object({
  sent: z.boolean(),
  telegram_ready: z.boolean(),
  detail: z.string(),
  delivery_id: z.number().nullable().optional(),
});

export type TelegramTestResponse = z.infer<typeof TelegramTestResponseSchema>;

export const ApiErrorResponseSchema = z.object({
  detail: z.string(),
});

export const EmptyResponseSchema = z.object({});

export const LatestPriceSchema = z.object({
  instrument_id: z.number(),
  instrument_name: z.string(),
  source_mapping_id: z.number(),
  provider: z.string(),
  market_type: z.string(),
  symbol: z.string(),
  last_price: z.string(),
  last_observed_at: isoDateTime,
  last_error: z.string().nullable(),
  support_breached: z.boolean(),
  resistance_broken: z.boolean(),
});

export type LatestPrice = z.infer<typeof LatestPriceSchema>;

export const RecentAlertSchema = z.object({
  id: z.number(),
  instrument_id: z.number(),
  source_mapping_id: z.number(),
  alert_kind: z.string(),
  price: z.string(),
  message: z.string(),
  triggered_at: isoDateTime,
});

export type RecentAlert = z.infer<typeof RecentAlertSchema>;

export const SourceErrorSchema = z.object({
  instrument_id: z.number(),
  instrument_name: z.string(),
  source_mapping_id: z.number(),
  provider: z.string(),
  market_type: z.string(),
  symbol: z.string(),
  last_observed_at: isoDateTime,
  last_error: z.string(),
});

export type SourceError = z.infer<typeof SourceErrorSchema>;

const SourceMappingSchema = z.object({
  id: z.number(),
  provider: z.string(),
  market_type: z.string(),
  symbol: z.string(),
  enabled: z.boolean(),
});

const optionalLevelString = z.string().nullable().transform((v) => (v === null || v === "" ? null : v));
const levelStrings = z.array(z.string());

const InstrumentSchema = z.object({
  id: z.number(),
  name: z.string(),
  enabled: z.boolean(),
  alert_mode: z.enum(["static", "fixed_drawdown"]),
  supports: levelStrings,
  resistances: levelStrings,
  high_water: optionalLevelString,
  fixed_drawdown: optionalLevelString,
  near_support_threshold: optionalLevelString,
  risk_reward_threshold: optionalLevelString,
});

export const InstrumentWithMappingsSchema = InstrumentSchema.extend({
  source_mappings: z.array(SourceMappingSchema),
});

export type InstrumentWithMappings = z.infer<typeof InstrumentWithMappingsSchema>;

export type CreateInstrumentRequest = {
  name: string;
  enabled: boolean;
  alert_mode?: "static" | "fixed_drawdown";
  supports: string[];
  resistances: string[];
  high_water?: string;
  fixed_drawdown?: string;
  near_support_threshold: string;
  risk_reward_threshold: string;
  source_mappings: ReadonlyArray<{
    provider: string;
    market_type: string;
    symbol: string;
    enabled: boolean;
  }>;
};

type CreateInstrumentApiPayload = Omit<
  CreateInstrumentRequest,
  "supports" | "resistances" | "high_water" | "fixed_drawdown" | "near_support_threshold" | "risk_reward_threshold"
> & {
  readonly supports: string[];
  readonly resistances: string[];
  readonly high_water: string | null;
  readonly fixed_drawdown: string | null;
  readonly near_support_threshold: string | null;
  readonly risk_reward_threshold: string | null;
};

export function serializeInstrumentLevelsForApi(data: CreateInstrumentRequest): CreateInstrumentApiPayload {
  const supports = data.supports.map((level) => level.trim()).filter(Boolean);
  const resistances = data.resistances.map((level) => level.trim()).filter(Boolean);
  const fixedDrawdown = data.alert_mode === "fixed_drawdown";

  return {
    ...data,
    alert_mode: data.alert_mode ?? "static",
    supports: fixedDrawdown ? [] : supports,
    resistances,
    high_water: fixedDrawdown ? data.high_water?.trim() || null : null,
    fixed_drawdown: fixedDrawdown ? data.fixed_drawdown?.trim() || null : null,
    near_support_threshold:
      supports.length === 0 && !fixedDrawdown ? null : data.near_support_threshold.trim() || null,
    risk_reward_threshold:
      (supports.length === 0 && !fixedDrawdown) || resistances.length === 0
        ? null
        : data.risk_reward_threshold.trim() || null,
  };
}

const SymbolOptionSchema = z.object({
  symbol: z.string(),
  label: z.string(),
  provider: z.string(),
  market_type: z.string(),
});

export type SymbolOption = z.infer<typeof SymbolOptionSchema>;

export const SymbolQueryResponseSchema = z.object({
  options: z.array(SymbolOptionSchema),
});
