import { z } from "zod";

export const HealthResponseSchema = z.object({
  status: z.string(),
  telegram_ready: z.boolean(),
});

export type HealthResponse = z.infer<typeof HealthResponseSchema>;

export const RuntimeResponseSchema = z.object({
  scheduler_ready: z.boolean(),
  providers_ready: z.boolean(),
  telegram_ready: z.boolean(),
});

export type RuntimeResponse = z.infer<typeof RuntimeResponseSchema>;

export const TelegramTestResponseSchema = z.object({
  sent: z.boolean(),
  telegram_ready: z.boolean(),
  detail: z.string(),
});

export type TelegramTestResponse = z.infer<typeof TelegramTestResponseSchema>;

export const LatestPriceSchema = z.object({
  instrument_id: z.string(),
  source_id: z.string(),
  price: z.string(),
  timestamp: z.string(),
});

export type LatestPrice = z.infer<typeof LatestPriceSchema>;

export const RecentAlertSchema = z.object({
  id: z.string(),
  instrument_id: z.string(),
  source_id: z.string(),
  price: z.string(),
  rule_type: z.string(),
  created_at: z.string(),
});

export type RecentAlert = z.infer<typeof RecentAlertSchema>;

export const SourceErrorSchema = z.object({
  source_id: z.string(),
  error_type: z.string(),
  message: z.string(),
  timestamp: z.string(),
});

export type SourceError = z.infer<typeof SourceErrorSchema>;

export const InstrumentSchema = z.object({
  id: z.string(),
  name: z.string(),
  enabled: z.boolean(),
  support: z.string(),
  resistance: z.string(),
  near_support_threshold: z.string(),
  risk_reward_threshold: z.string(),
});

export type Instrument = z.infer<typeof InstrumentSchema>;

export const SourceMappingSchema = z.object({
  id: z.string(),
  instrument_id: z.string(),
  provider: z.string(),
  market_type: z.string(),
  symbol: z.string(),
  enabled: z.boolean(),
});

export type SourceMapping = z.infer<typeof SourceMappingSchema>;

export const InstrumentWithMappingsSchema = InstrumentSchema.extend({
  source_mappings: z.array(SourceMappingSchema),
});

export type InstrumentWithMappings = z.infer<typeof InstrumentWithMappingsSchema>;

export const CreateInstrumentRequestSchema = z.object({
  name: z.string(),
  enabled: z.boolean(),
  support: z.string(),
  resistance: z.string(),
  near_support_threshold: z.string(),
  risk_reward_threshold: z.string(),
  source_mappings: z.array(z.object({
    provider: z.string(),
    market_type: z.string(),
    symbol: z.string(),
    enabled: z.boolean(),
  })),
});

export type CreateInstrumentRequest = z.infer<typeof CreateInstrumentRequestSchema>;

export const UpdateInstrumentRequestSchema = CreateInstrumentRequestSchema;
export type UpdateInstrumentRequest = z.infer<typeof UpdateInstrumentRequestSchema>;

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

    // For 204 No Content, return empty object (or null if schema allows, but we usually expect a schema)
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
    const options: RequestInit = {};
    if (signal) {
      options.signal = signal;
    }
    return this.fetch("/api/runtime", RuntimeResponseSchema, options);
  }

  async getLatestPrices(signal?: AbortSignal): Promise<readonly LatestPrice[]> {
    const options: RequestInit = {};
    if (signal) {
      options.signal = signal;
    }
    return this.fetch("/api/prices/latest", z.array(LatestPriceSchema), options);
  }

  async getRecentAlerts(signal?: AbortSignal): Promise<readonly RecentAlert[]> {
    const options: RequestInit = {};
    if (signal) {
      options.signal = signal;
    }
    return this.fetch("/api/alerts", z.array(RecentAlertSchema), options);
  }

  async getSourceErrors(signal?: AbortSignal): Promise<readonly SourceError[]> {
    const options: RequestInit = {};
    if (signal) {
      options.signal = signal;
    }
    return this.fetch("/api/source-errors", z.array(SourceErrorSchema), options);
  }

  async testTelegram(signal?: AbortSignal): Promise<TelegramTestResponse> {
    const options: RequestInit = {
      method: "POST",
    };
    if (signal) {
      options.signal = signal;
    }
    return this.fetch("/api/telegram/test", TelegramTestResponseSchema, options);
  }

  async getInstruments(signal?: AbortSignal): Promise<readonly InstrumentWithMappings[]> {
    const options: RequestInit = {};
    if (signal) {
      options.signal = signal;
    }
    return this.fetch("/api/instruments", z.array(InstrumentWithMappingsSchema), options);
  }

  async getInstrument(id: string, signal?: AbortSignal): Promise<InstrumentWithMappings> {
    const options: RequestInit = {};
    if (signal) {
      options.signal = signal;
    }
    return this.fetch(`/api/instruments/${id}`, InstrumentWithMappingsSchema, options);
  }

  async createInstrument(data: CreateInstrumentRequest, signal?: AbortSignal): Promise<InstrumentWithMappings> {
    const options: RequestInit = {
      method: "POST",
      body: JSON.stringify(data),
    };
    if (signal) {
      options.signal = signal;
    }
    return this.fetch("/api/instruments", InstrumentWithMappingsSchema, options);
  }

  async updateInstrument(id: string, data: UpdateInstrumentRequest, signal?: AbortSignal): Promise<InstrumentWithMappings> {
    const options: RequestInit = {
      method: "PUT",
      body: JSON.stringify(data),
    };
    if (signal) {
      options.signal = signal;
    }
    return this.fetch(`/api/instruments/${id}`, InstrumentWithMappingsSchema, options);
  }

  async deleteInstrument(id: string, signal?: AbortSignal): Promise<void> {
    const options: RequestInit = {
      method: "DELETE",
    };
    if (signal) {
      options.signal = signal;
    }
    await this.fetch(`/api/instruments/${id}`, z.object({}), options);
  }
}

export const apiClient = new ApiClient(
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
);
