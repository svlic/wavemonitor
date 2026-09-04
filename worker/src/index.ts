import { Hono } from "hono";
import { deleteCookie, getCookie, setCookie } from "hono/cookie";
import { ZodError, z } from "zod";
import { createInstrument, getInstrument, instrumentResponse, listInstruments, patchInstrument, randomId, replaceInstrument } from "./database";
import { runMonitoringTick } from "./monitor";
import { querySymbols } from "./providers";
import { escapeMarkdown, sendTelegram } from "./telegram";
import type { Env } from "./types";
import { authSchema, enabledPatchSchema, instrumentSchema, isMarketType, isProvider } from "./validation";

const app = new Hono<{ Bindings: Env }>();
const SESSION_COOKIE = "wavemonitor_session";
const SESSION_VALUE = "authenticated";

function telegramReady(env: Env): boolean {
  return Boolean(env.TELEGRAM_BOT_TOKEN && env.TELEGRAM_CHAT_ID);
}

async function sessionValue(env: Env): Promise<string> {
  if (!env.WAVEMONITOR_SESSION_SECRET) throw new Error("WAVEMONITOR_SESSION_SECRET is required when web authentication is enabled");
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.WAVEMONITOR_SESSION_SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(SESSION_VALUE));
  const encoded = btoa(String.fromCharCode(...new Uint8Array(signature))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${SESSION_VALUE}.${encoded}`;
}

async function authenticated(cookie: string | undefined, env: Env): Promise<boolean> {
  if (!env.WAVEMONITOR_WEB_PASSWORD) return true;
  if (!cookie) return false;
  return cookie === await sessionValue(env);
}

app.use("/api/*", async (context, next) => {
  const path = new URL(context.req.url).pathname;
  if (path.startsWith("/api/auth/")) return next();
  if (!await authenticated(getCookie(context, SESSION_COOKIE), context.env)) return context.json({ detail: "Authentication required" }, 401);
  return next();
});

app.get("/health", (context) => context.json({ status: "ok", telegram_ready: telegramReady(context.env) }));
app.get("/api/auth/session", async (context) => {
  const authEnabled = Boolean(context.env.WAVEMONITOR_WEB_PASSWORD);
  return context.json({ authenticated: authEnabled ? await authenticated(getCookie(context, SESSION_COOKIE), context.env) : false, auth_enabled: authEnabled });
});
app.post("/api/auth/login", async (context) => {
  const body = authSchema.parse(await context.req.json());
  if (!context.env.WAVEMONITOR_WEB_PASSWORD) return context.json({ authenticated: false, auth_enabled: false });
  if (body.password !== context.env.WAVEMONITOR_WEB_PASSWORD) return context.json({ detail: "Invalid password" }, 401);
  setCookie(context, SESSION_COOKIE, await sessionValue(context.env), { httpOnly: true, sameSite: "Lax", secure: true, maxAge: 7 * 24 * 60 * 60, path: "/" });
  return context.json({ authenticated: true, auth_enabled: true });
});
app.post("/api/auth/logout", (context) => {
  deleteCookie(context, SESSION_COOKIE, { sameSite: "Lax", secure: true, path: "/" });
  return context.json({ authenticated: false, auth_enabled: Boolean(context.env.WAVEMONITOR_WEB_PASSWORD) });
});

app.get("/api/instruments", async (context) => context.json(await listInstruments(context.env.DB)));
app.post("/api/instruments", async (context) => {
  const input = instrumentSchema.parse(await context.req.json());
  const response = await createInstrument(context.env.DB, input);
  return context.json(response, 201);
});
app.put("/api/instruments/:id", async (context) => {
  const id = Number(context.req.param("id"));
  const row = Number.isSafeInteger(id) ? await getInstrument(context.env.DB, id) : null;
  if (row === null) return context.json({ detail: "Instrument not found" }, 404);
  const input = instrumentSchema.parse(await context.req.json());
  const response = await replaceInstrument(context.env.DB, row, input);
  return context.json(response);
});
app.patch("/api/instruments/:id", async (context) => {
  const id = Number(context.req.param("id"));
  const row = Number.isSafeInteger(id) ? await getInstrument(context.env.DB, id) : null;
  if (row === null) return context.json({ detail: "Instrument not found" }, 404);
  const body = enabledPatchSchema.parse(await context.req.json());
  const response = await patchInstrument(context.env.DB, row, body.enabled);
  return context.json(response);
});
app.delete("/api/instruments/:id", async (context) => {
  const id = Number(context.req.param("id"));
  const row = Number.isSafeInteger(id) ? await getInstrument(context.env.DB, id) : null;
  if (row === null) return context.json({ detail: "Instrument not found" }, 404);
  await context.env.DB.prepare("DELETE FROM instrument WHERE id=?").bind(id).run();
  return context.body(null, 204);
});

app.get("/api/instruments/:id/status", async (context) => {
  const id = Number(context.req.param("id"));
  const row = Number.isSafeInteger(id) ? await getInstrument(context.env.DB, id) : null;
  if (row === null) return context.json({ detail: "Instrument not found" }, 404);
  const sources = await context.env.DB.prepare("WITH ranked AS (SELECT p.*,ROW_NUMBER() OVER(PARTITION BY source_mapping_id ORDER BY observed_at DESC,id DESC) rn,ROW_NUMBER() OVER(PARTITION BY source_mapping_id ORDER BY CASE WHEN error IS NULL AND price IS NOT NULL THEN 0 ELSE 1 END,observed_at DESC,id DESC) success_rn FROM price_observation p) SELECT s.id,s.provider,s.market_type,s.symbol,s.enabled,ok.price last_price,ok.observed_at last_observed_at,last.error last_error,st.last_invalid_state FROM source_mapping s LEFT JOIN ranked last ON last.source_mapping_id=s.id AND last.rn=1 LEFT JOIN ranked ok ON ok.source_mapping_id=s.id AND ok.success_rn=1 AND ok.error IS NULL AND ok.price IS NOT NULL LEFT JOIN last_rule_state st ON st.source_mapping_id=s.id WHERE s.instrument_id=? ORDER BY s.id").bind(id).all<Record<string, unknown>>();
  const alerts = await context.env.DB.prepare("SELECT id,instrument_id,source_mapping_id,alert_kind,price,message,triggered_at FROM alert_event WHERE instrument_id=? ORDER BY triggered_at DESC LIMIT 10").bind(id).all();
  return context.json({ instrument_id: id, enabled: Boolean(row.enabled), sources: sources.results.map((source) => ({ ...source, enabled: Boolean(source.enabled) })), recent_alerts: alerts.results });
});

app.get("/api/alerts", async (context) => {
  const rows = await context.env.DB.prepare("SELECT id,instrument_id,source_mapping_id,alert_kind,price,message,triggered_at FROM alert_event ORDER BY triggered_at DESC LIMIT 50").all();
  return context.json(rows.results);
});
app.get("/api/prices/latest", async (context) => {
  const rows = await context.env.DB.prepare("WITH latest AS (SELECT p.*,ROW_NUMBER() OVER(PARTITION BY source_mapping_id ORDER BY observed_at DESC,id DESC) rn FROM price_observation p WHERE error IS NULL AND price IS NOT NULL),crossings AS (SELECT a.source_mapping_id,MAX(a.alert_kind='support_breach') support_breached,MAX(a.alert_kind='resistance_breakout') resistance_broken FROM alert_event a JOIN instrument i ON i.id=a.instrument_id AND i.rule_cycle_started_at=a.rule_cycle_started_at GROUP BY a.source_mapping_id) SELECT i.id instrument_id,i.name instrument_name,s.id source_mapping_id,s.provider,s.market_type,s.symbol,p.price last_price,p.observed_at last_observed_at,NULL last_error,COALESCE(c.support_breached,0) support_breached,COALESCE(c.resistance_broken,0) resistance_broken FROM instrument i JOIN source_mapping s ON s.instrument_id=i.id JOIN latest p ON p.source_mapping_id=s.id AND p.rn=1 LEFT JOIN crossings c ON c.source_mapping_id=s.id WHERE i.enabled=1 AND s.enabled=1 ORDER BY i.id,s.id").all<Record<string, unknown>>();
  return context.json(rows.results.map((row) => ({ ...row, support_breached: Boolean(row.support_breached), resistance_broken: Boolean(row.resistance_broken) })));
});
app.get("/api/source-errors", async (context) => {
  const rows = await context.env.DB.prepare("WITH latest AS (SELECT p.*,ROW_NUMBER() OVER(PARTITION BY source_mapping_id ORDER BY observed_at DESC,id DESC) rn FROM price_observation p) SELECT i.id instrument_id,i.name instrument_name,s.id source_mapping_id,s.provider,s.market_type,s.symbol,p.observed_at last_observed_at,p.error last_error FROM instrument i JOIN source_mapping s ON s.instrument_id=i.id JOIN latest p ON p.source_mapping_id=s.id AND p.rn=1 WHERE i.enabled=1 AND s.enabled=1 AND p.error IS NOT NULL ORDER BY i.id,s.id").all();
  return context.json(rows.results);
});
app.get("/api/runtime", async (context) => {
  const row = await context.env.DB.prepare("SELECT * FROM runtime_state WHERE singleton=1").first<Record<string, unknown>>();
  return context.json({ scheduler_ready: Boolean(row?.scheduler_ready), providers_ready: Boolean(row?.providers_ready), telegram_ready: telegramReady(context.env), enabled_sources: Number(row?.enabled_sources ?? 0), polled_sources: Number(row?.polled_sources ?? 0), observations_written: Number(row?.observations_written ?? 0), source_errors: Number(row?.source_errors ?? 0), alert_events_created: Number(row?.alert_events_created ?? 0), telegram_deliveries_attempted: Number(row?.telegram_deliveries_attempted ?? 0), last_tick_started_at: row?.last_tick_started_at ?? null, last_tick_finished_at: row?.last_tick_finished_at ?? null });
});
app.get("/api/telegram/readiness", (context) => context.json({ telegram_ready: telegramReady(context.env) }));
app.post("/api/telegram/test", async (context) => {
  if (!telegramReady(context.env)) return context.json({ sent: false, telegram_ready: false, detail: "Telegram credentials are not configured.", delivery_id: null }, 503);
  const text = escapeMarkdown("WaveMonitor Telegram test message.");
  const result = await sendTelegram(context.env, text);
  if (result === null) return context.json({ sent: false, telegram_ready: false, detail: "Telegram credentials are not configured.", delivery_id: null }, 503);
  const deliveryId = randomId();
  await context.env.DB.prepare("INSERT INTO telegram_delivery(id,status,message_kind,message_text,chat_ref,telegram_message_id,safe_error,delivered_at) VALUES(?,?,?,?,?,?,?,?)").bind(deliveryId, result.status, "test", text, "redacted", result.messageId, result.safeError, new Date().toISOString()).run();
  return context.json({ sent: result.status === "sent", telegram_ready: true, detail: result.status === "sent" ? "Telegram test message delivered." : result.safeError!, delivery_id: deliveryId }, result.status === "sent" ? 200 : 502);
});
app.get("/api/symbols/query", async (context) => {
  const provider = context.req.query("provider") ?? ""; const marketType = context.req.query("market_type") ?? ""; const query = context.req.query("q")?.trim() ?? "";
  if (!isProvider(provider) || !isMarketType(marketType) || !query) return context.json({ detail: "Invalid symbol query" }, 422);
  return context.json({ options: await querySymbols(provider, marketType, query) });
});

app.onError((error, context) => {
  if (error instanceof ZodError) return context.json({ detail: error.issues.map((issue) => issue.message).join("; ") }, 422);
  const message = error instanceof Error ? error.message : "Internal server error";
  if (message.includes("UNIQUE constraint failed")) return context.json({ detail: "Source mapping already exists" }, 409);
  console.error("request failed", { message });
  return context.json({ detail: "Internal server error" }, 500);
});
app.notFound((context) => context.env.ASSETS.fetch(context.req.raw));

export default {
  fetch: app.fetch,
  async scheduled(_controller: ScheduledController, env: Env, context: ExecutionContext): Promise<void> {
    context.waitUntil(runMonitoringTick(env));
  },
};
