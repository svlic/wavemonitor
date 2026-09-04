import { applyD1Migrations, env, SELF } from "cloudflare:test";
import { beforeAll, describe, expect, it } from "vitest";

declare module "cloudflare:test" {
  interface ProvidedEnv { DB: D1Database; TEST_MIGRATIONS: D1Migration[] }
}

beforeAll(async () => applyD1Migrations(env.DB, env.TEST_MIGRATIONS));

describe("worker API", () => {
  it("reports health and empty runtime", async () => {
    const health = await SELF.fetch("https://example.com/health");
    expect(await health.json()).toEqual({ status: "ok", telegram_ready: false });
    const runtime = await SELF.fetch("https://example.com/api/runtime");
    expect(await runtime.json()).toMatchObject({ scheduler_ready: false, enabled_sources: 0, last_tick_finished_at: null });
  });

  it("creates, lists, patches, replaces, and deletes an instrument", async () => {
    const payload = { name: "Bitcoin", enabled: true, supports: ["90000.10"], resistances: ["110000.25"], near_support_threshold: "0.02", risk_reward_threshold: "3.5", source_mappings: [{ provider: "binance", market_type: "usd_m_futures", symbol: "btcusdt", enabled: false }] };
    const createdResponse = await SELF.fetch("https://example.com/api/instruments", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
    expect(createdResponse.status).toBe(201);
    const created = await createdResponse.json<{ id: number; supports: string[]; source_mappings: Array<{ id: number; symbol: string }> }>();
    expect(created.supports).toEqual(["90000.1000000000"]);
    expect(created.source_mappings[0]?.symbol).toBe("BTCUSDT");
    const sourceId = created.source_mappings[0]!.id;
    const patched = await SELF.fetch(`https://example.com/api/instruments/${created.id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ enabled: false }) });
    expect((await patched.json<{ enabled: boolean }>()).enabled).toBe(false);
    const replaced = await SELF.fetch(`https://example.com/api/instruments/${created.id}`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ ...payload, name: "Bitcoin setup" }) });
    const replacement = await replaced.json<{ name: string; source_mappings: Array<{ id: number }> }>();
    expect(replacement.name).toBe("Bitcoin setup");
    expect(replacement.source_mappings[0]?.id).toBe(sourceId);
    const deleted = await SELF.fetch(`https://example.com/api/instruments/${created.id}`, { method: "DELETE" });
    expect(deleted.status).toBe(204);
    expect(await (await SELF.fetch("https://example.com/api/instruments")).json()).toEqual([]);
  });

  it("rejects invalid provider-market pairs", async () => {
    const response = await SELF.fetch("https://example.com/api/instruments", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: "Bad", supports: ["1"], near_support_threshold: "0.1", source_mappings: [{ provider: "yfinance", market_type: "perpetual", symbol: "BTC" }] }) });
    expect(response.status).toBe(422);
  });
});
