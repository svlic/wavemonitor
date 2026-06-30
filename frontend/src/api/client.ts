import { z } from "zod";

const isoDateTime = z.union([z.string(), z.number()]).transform((v) =>
  typeof v === "number" ? new Date(v).toISOString() : v,
);

const RuntimeResponseSchema = z.object({
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

const TelegramTestResponseSchema = z.object({
  sent: z.boolean(),
  telegram_ready: z.boolean(),
  detail: z.string(),
  delivery_id: z.number().nullable().optional(),
});

export type TelegramTestResponse = z.infer<typeof TelegramTestResponseSchema>;

const LatestPriceSchema = z.object({
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

const RecentAlertSchema = z.object({
  id: z.number(),
  instrument_id: z.number(),
  source_mapping_id: z.number(),
  alert_kind: z.string(),
  price: z.string(),
  message: z.string(),
  triggered_at: isoDateTime,
});

export type RecentAlert = z.infer<typeof RecentAlertSchema>;

const SourceErrorSchema = z.object({
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

type SourceMapping = z.infer<typeof SourceMappingSchema>;

const InstrumentSchema = z.object({
  id: z.number(),
  name: z.string(),
  enabled: z.boolean(),
  support: z.string(),
  resistance: z.string(),
  near_support_threshold: z.string(),
  risk_reward_threshold: z.string(),
});

type Instrument = z.infer<typeof InstrumentSchema>;

const InstrumentWithMappingsSchema = InstrumentSchema.extend({
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

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class ApiClient {
  constructor(private readonly baseUrl: string) {}

  private requestInit(signal?: AbortSignal, init: RequestInit = {}): RequestInit {
    if (signal === undefined) {
      return init;
    }
    return { ...init, signal };
  }

  private async fetch<T>(
    path: string,
    schema: z.ZodType<T>,
    options?: RequestInit,
  ): Promise<T> {
    const url = new URL(path, this.baseUrl);
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new ApiError(response.status, `API request failed: ${response.statusText}`);
    }

    if (response.status === 204) {
      const result = schema.safeParse({});
      if (!result.success) {
        throw new ApiError(500, `Invalid API response: ${result.error.message}`);
      }
      return result.data;
    }

    const data = await response.json();
    const result = schema.safeParse(data);

    if (!result.success) {
      throw new ApiError(500, `Invalid API response: ${result.error.message}`);
    }

    return result.data;
  }

  async getRuntime(signal?: AbortSignal): Promise<RuntimeResponse> {
    return this.fetch("/api/runtime", RuntimeResponseSchema, this.requestInit(signal));
  }

  async getLatestPrices(signal?: AbortSignal): Promise<readonly LatestPrice[]> {
    return this.fetch("/api/prices/latest", z.array(LatestPriceSchema), this.requestInit(signal));
  }

  async getRecentAlerts(signal?: AbortSignal): Promise<readonly RecentAlert[]> {
    return this.fetch("/api/alerts", z.array(RecentAlertSchema), this.requestInit(signal));
  }

  async getSourceErrors(signal?: AbortSignal): Promise<readonly SourceError[]> {
    return this.fetch("/api/source-errors", z.array(SourceErrorSchema), this.requestInit(signal));
  }

  async testTelegram(signal?: AbortSignal): Promise<TelegramTestResponse> {
    return this.fetch(
      "/api/telegram/test",
      TelegramTestResponseSchema,
      this.requestInit(signal, { method: "POST" }),
    );
  }

  async getInstruments(signal?: AbortSignal): Promise<readonly InstrumentWithMappings[]> {
    return this.fetch(
      "/api/instruments",
      z.array(InstrumentWithMappingsSchema),
      this.requestInit(signal),
    );
  }

  async getInstrument(id: number | string, signal?: AbortSignal): Promise<InstrumentWithMappings> {
    const numericId = typeof id === "string" ? Number(id) : id;
    const instruments = await this.getInstruments(signal);
    const match = instruments.find((item) => item.id === numericId);
    if (match === undefined) {
      throw new ApiError(404, `Instrument ${id} not found`);
    }
    return match;
  }

  async createInstrument(
    data: CreateInstrumentRequest,
    signal?: AbortSignal,
  ): Promise<InstrumentWithMappings> {
    return this.fetch(
      "/api/instruments",
      InstrumentWithMappingsSchema,
      this.requestInit(signal, { method: "POST", body: JSON.stringify(data) }),
    );
  }

  async updateInstrument(
    id: number | string,
    data: CreateInstrumentRequest,
    signal?: AbortSignal,
  ): Promise<InstrumentWithMappings> {
    const pathId = typeof id === "string" ? id : String(id);
    return this.fetch(
      `/api/instruments/${pathId}`,
      InstrumentWithMappingsSchema,
      this.requestInit(signal, { method: "PUT", body: JSON.stringify(data) }),
    );
  }

  async deleteInstrument(id: number | string, signal?: AbortSignal): Promise<void> {
    const pathId = typeof id === "string" ? id : String(id);
    await this.fetch(`/api/instruments/${pathId}`, z.object({}), this.requestInit(signal, { method: "DELETE" }));
  }
}

export const apiClient = new ApiClient(import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000");