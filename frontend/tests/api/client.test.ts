import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "../../src/api/client";

describe("ApiClient", () => {
  const client = new ApiClient("http://test.local");

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws ApiError on non-200 response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("Internal Server Error", { status: 500, statusText: "Internal Server Error" }),
    );

    await expect(client.getRuntime()).rejects.toThrow(ApiError);
  });

  it("throws ApiError on invalid response schema", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ invalid: "data" }), { status: 200 }),
    );

    await expect(client.getRuntime()).rejects.toThrow(ApiError);
  });

  it("returns parsed data on success", async () => {
    const mockData = {
      scheduler_ready: true,
      providers_ready: true,
      telegram_ready: false,
    };

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(mockData), { status: 200 }),
    );

    const result = await client.getRuntime();
    expect(result).toEqual(mockData);
  });
});
