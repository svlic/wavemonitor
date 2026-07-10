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
});

export type AuthStatusResponse = z.infer<typeof AuthStatusResponseSchema>;

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

const optionalLevelString = z
  .string()
  .nullable()
  .transform((v) => (v === null || v === "" ? null : v));

const InstrumentSchema = z.object({
  id: z.number(),
  name: z.string(),
  enabled: z.boolean(),
  support: optionalLevelString,
  resistance: optionalLevelString,
  near_support_threshold: z.string(),
  risk_reward_threshold: z.string(),
});

export const InstrumentWithMappingsSchema = InstrumentSchema.extend({
  source_mappings: z.array(SourceMappingSchema),
});

export type InstrumentWithMappings = z.infer<typeof InstrumentWithMappingsSchema>;

const CreateInstrumentRequestSchema = z.object({
  name: z.string(),
  enabled: z.boolean(),
  support: z.string(),
  resistance: z.string(),
  near_support_threshold: z.string(),
  risk_reward_threshold: z.string(),
  source_mappings: z.array(
    z.object({
      provider: z.string(),
      market_type: z.string(),
      symbol: z.string(),
      enabled: z.boolean(),
    }),
  ),
});

export type CreateInstrumentRequest = z.infer<typeof CreateInstrumentRequestSchema>;

export type CreateInstrumentApiPayload = Omit<CreateInstrumentRequest, "support" | "resistance"> & {
  readonly support: string | null;
  readonly resistance: string | null;
};

export function serializeInstrumentLevelsForApi(data: CreateInstrumentRequest): CreateInstrumentApiPayload {
  return {
    ...data,
    support: data.support.trim() || null,
    resistance: data.resistance.trim() || null,
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
