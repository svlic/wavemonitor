import { loadTelegramCredentials } from "./config";
import { decimal, emptyRuleState, evaluateRules, fixed, nearestPair } from "./rules";
import { fetchPrice } from "./providers";
import { alertMessage, sendTelegram } from "./telegram";
import type { AlertDecision, EnabledSource, Env, RuleState } from "./types";

interface StateRow extends RuleState { instrument_id: number; source_mapping_id: number; updated_at: string }
interface PendingAlert { source: EnabledSource; alert: AlertDecision }
interface DeliveryRow { status: "sent" | "failed"; messageKind: string; messageText: string; messageId: string | null; safeError: string | null; deliveredAt: string }

function placeholders(rows: number, columns: number): string {
  return Array.from({ length: rows }, () => `(${Array(columns).fill("?").join(",")})`).join(",");
}
function chunks<T>(values: T[], size: number): T[][] {
  const result: T[][] = [];
  for (let index = 0; index < values.length; index += size) {
    result.push(values.slice(index, index + size));
  }
  return result;
}


async function insertObservations(db: D1Database, rows: Array<[number, string | null, string, string | null, string | null]>): Promise<void> {
  for (const group of chunks(rows, 20)) {
    await db.prepare(`INSERT INTO price_observation(source_mapping_id,price,observed_at,raw_path,error) VALUES ${placeholders(group.length, 5)}`).bind(...group.flat()).run();
  }
}

async function upsertStates(db: D1Database, rows: Array<[number, number, RuleState, string]>): Promise<void> {
  for (const group of chunks(rows, 6)) {
    const values = group.flatMap(([instrumentId, sourceId, state, updatedAt]) => [instrumentId, sourceId, state.last_price, state.near_support_active, state.risk_reward_active, state.above_resistance_active, state.support_breach_active, state.near_support_last_alert_at, state.risk_reward_last_alert_at, state.breakout_last_alert_at, state.support_breach_last_alert_at, state.last_invalid_state, updatedAt]);
    await db.prepare(`INSERT INTO last_rule_state(instrument_id,source_mapping_id,last_price,near_support_active,risk_reward_active,above_resistance_active,support_breach_active,near_support_last_alert_at,risk_reward_last_alert_at,breakout_last_alert_at,support_breach_last_alert_at,last_invalid_state,updated_at) VALUES ${placeholders(group.length, 13)} ON CONFLICT(instrument_id,source_mapping_id) DO UPDATE SET last_price=excluded.last_price,near_support_active=excluded.near_support_active,risk_reward_active=excluded.risk_reward_active,above_resistance_active=excluded.above_resistance_active,support_breach_active=excluded.support_breach_active,near_support_last_alert_at=excluded.near_support_last_alert_at,risk_reward_last_alert_at=excluded.risk_reward_last_alert_at,breakout_last_alert_at=excluded.breakout_last_alert_at,support_breach_last_alert_at=excluded.support_breach_last_alert_at,last_invalid_state=excluded.last_invalid_state,updated_at=excluded.updated_at`).bind(...values).run();
  }
}

async function claimAlerts(db: D1Database, pending: PendingAlert[]): Promise<PendingAlert[]> {
  const claimed: PendingAlert[] = [];
  for (const { source, alert } of pending) {
    const result = await db.prepare("INSERT INTO alert_event(instrument_id,source_mapping_id,alert_kind,price,support,resistance,threshold,message,triggered_at,rule_cycle_started_at) SELECT ?,?,?,?,?,?,?,?,?,? WHERE EXISTS (SELECT 1 FROM instrument WHERE id=? AND rule_cycle_started_at=?) ON CONFLICT(instrument_id,source_mapping_id,alert_kind,rule_cycle_started_at) DO NOTHING RETURNING id").bind(source.instrument_id, source.id, alert.kind, alert.price, alert.support, alert.resistance, alert.threshold, alert.message, alert.triggered_at, source.rule_cycle_started_at, source.instrument_id, source.rule_cycle_started_at).first<{ id: number }>();
    if (result !== null) claimed.push({ source, alert });
  }
  return claimed;
}

async function insertDeliveries(db: D1Database, rows: DeliveryRow[]): Promise<void> {
  for (const group of chunks(rows, 14)) {
    const values = group.flatMap((row) => [row.status, row.messageKind, row.messageText, "redacted", row.messageId, row.safeError, row.deliveredAt]);
    await db.prepare(`INSERT INTO telegram_delivery(status,message_kind,message_text,chat_ref,telegram_message_id,safe_error,delivered_at) VALUES ${placeholders(group.length, 7)}`).bind(...values).run();
  }
}

export async function runMonitoringTick(env: Env): Promise<void> {
  const startedAt = new Date().toISOString();
  const telegramCredentials = await loadTelegramCredentials(env);
  const sourceRows = await env.DB.prepare("SELECT s.*,i.name AS instrument_name,i.alert_mode,i.supports,i.resistances,i.high_water,i.fixed_drawdown,i.near_support_threshold,i.risk_reward_threshold,i.rule_cycle_started_at FROM source_mapping s JOIN instrument i ON i.id=s.instrument_id WHERE i.enabled=1 AND s.enabled=1 ORDER BY s.id").all<EnabledSource>();
  const sources = sourceRows.results;
  const stateRows = await env.DB.prepare("SELECT * FROM last_rule_state").all<StateRow>();
  const stateBySource = new Map(stateRows.results.map((row) => [row.source_mapping_id, row]));
  const observations: Array<[number, string | null, string, string | null, string | null]> = [];
  const states: Array<[number, number, RuleState, string]> = [];
  const pendingAlerts: PendingAlert[] = [];
  let successes = 0;
  let errors = 0;

  const results = await Promise.all(sources.map(async (source) => {
    try {
      return { source, result: await fetchPrice(source) };
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown provider error";
      return { source, result: { ok: false as const, error: `provider_error: ${message}`.slice(0, 500) } };
    }
  }));
  for (const { source, result } of results) {
    const observedAt = new Date().toISOString();
    if (!result.ok) {
      observations.push([source.id, null, observedAt, null, result.error]);
      errors++;
      continue;
    }
    observations.push([source.id, result.price, observedAt, result.path, null]);
    successes++;
    const supports = JSON.parse(source.supports) as string[];
    const resistances = JSON.parse(source.resistances) as string[];
    const [support, resistance] = nearestPair(supports, resistances, result.price);
    const persisted = stateBySource.get(source.id);
    const previous = persisted !== undefined && persisted.updated_at >= source.rule_cycle_started_at
      ? persisted
      : emptyRuleState();
    const fallbackSupport = supports.length > 0
      ? fixed(supports.map(decimal).reduce((a, b) => a.lt(b) ? a : b))
      : null;
    const evaluation = evaluateRules({
      price: result.price,
      support: support ?? fallbackSupport,
      resistance,
      nearSupportThreshold: source.near_support_threshold,
      riskRewardThreshold: source.risk_reward_threshold,
      previous,
      observedAt,
    });
    const nextState = evaluation.nextState;
    const stateChanged = persisted === undefined
      || persisted.updated_at < source.rule_cycle_started_at
      || Object.keys(nextState).some(
        (key) => nextState[key as keyof RuleState] !== persisted[key as keyof RuleState],
      );
    if (stateChanged) states.push([source.instrument_id, source.id, nextState, observedAt]);
    pendingAlerts.push(...evaluation.alerts.map((alert) => ({ source, alert })));
  }

  await insertObservations(env.DB, observations);
  await upsertStates(env.DB, states);
  const claimed = await claimAlerts(env.DB, pendingAlerts);
  const deliveries: DeliveryRow[] = [];
  for (const item of claimed) {
    const message = alertMessage(item.source, item.alert);
    const result = await sendTelegram(telegramCredentials, message);
    if (result !== null) {
      deliveries.push({
        status: result.status,
        messageKind: "alert",
        messageText: message,
        messageId: result.messageId,
        safeError: result.safeError,
        deliveredAt: new Date().toISOString(),
      });
    }
  }
  await insertDeliveries(env.DB, deliveries);
  await env.DB.batch([
    env.DB.prepare("DELETE FROM price_observation WHERE observed_at < ?").bind(
      new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
    ),
    env.DB.prepare("UPDATE runtime_state SET scheduler_ready=1,providers_ready=?,enabled_sources=?,polled_sources=?,observations_written=?,source_errors=?,alert_events_created=?,telegram_deliveries_attempted=?,last_tick_started_at=?,last_tick_finished_at=? WHERE singleton=1").bind(
      Number(errors === 0),
      sources.length,
      sources.length,
      successes,
      errors,
      claimed.length,
      deliveries.length,
      startedAt,
      new Date().toISOString(),
    ),
  ]);
}
