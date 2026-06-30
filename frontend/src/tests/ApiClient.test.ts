import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "../api/client";

const runtimeResponse = {
  scheduler_ready: false,
  providers_ready: false,
  telegram_ready: false,
  enabled_sources: 0,
  polled_sources: 0,
  observations_written: 0,
  source_errors: 0,
  alert_events_created: 0,
  telegram_deliveries_attempted: 0,
  last_tick_started_at: null,
  last_tick_finished_at: null,
};

function stubFetch(response: Response) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();
  fetchMock.mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("ApiClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses same-origin API paths when no base URL is configured", async () => {
    const fetchMock = stubFetch(new Response(JSON.stringify(runtimeResponse), { status: 200 }));
    const client = new ApiClient("");

    await client.getRuntime();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runtime",
      expect.objectContaining({
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it("surfaces backend error detail for failed telegram test requests", async () => {
    stubFetch(
      new Response(JSON.stringify({ detail: "Telegram delivery failed with HTTP 401." }), {
        status: 502,
        statusText: "Bad Gateway",
      }),
    );
    const client = new ApiClient("");

    await expect(client.testTelegram()).rejects.toEqual(
      new ApiError(502, "Telegram delivery failed with HTTP 401."),
    );
  });
});
