import type { Instrument, RuleState, SourceMapping } from "./types";
import type { InstrumentInput } from "./validation";

export interface InstrumentResponse {
  id: number; name: string; enabled: boolean; alert_mode: "static" | "fixed_drawdown"; supports: string[]; resistances: string[]; high_water: string | null; fixed_drawdown: string | null; near_support_threshold: string | null; risk_reward_threshold: string | null; source_mappings: Array<{ id: number; provider: string; market_type: string; symbol: string; enabled: boolean }>;
}

export function randomId(): number {
  const words = new Uint32Array(1); crypto.getRandomValues(words);
  return (words[0]! & 0x7fffffff) || 1;
}

function parseLevels(value: string): string[] {
  const parsed: unknown = JSON.parse(value);
  return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
}

export async function instrumentResponse(db: D1Database, instrument: Instrument): Promise<InstrumentResponse> {
  const sources = await db.prepare("SELECT * FROM source_mapping WHERE instrument_id = ? ORDER BY id").bind(instrument.id).all<SourceMapping>();
  return { id: instrument.id, name: instrument.name, enabled: Boolean(instrument.enabled), alert_mode: instrument.alert_mode, supports: parseLevels(instrument.supports), resistances: parseLevels(instrument.resistances), high_water: instrument.high_water, fixed_drawdown: instrument.fixed_drawdown, near_support_threshold: instrument.near_support_threshold, risk_reward_threshold: instrument.risk_reward_threshold, source_mappings: sources.results.map((source) => ({ id: source.id, provider: source.provider, market_type: source.market_type, symbol: source.symbol, enabled: Boolean(source.enabled) })) };
}

export async function listInstruments(db: D1Database): Promise<InstrumentResponse[]> {
  const rows = await db.prepare("SELECT * FROM instrument ORDER BY id").all<Instrument>();
  return Promise.all(rows.results.map((row) => instrumentResponse(db, row)));
}

export async function getInstrument(db: D1Database, id: number): Promise<Instrument | null> {
  return db.prepare("SELECT * FROM instrument WHERE id = ?").bind(id).first<Instrument>();
}

export async function createInstrument(db: D1Database, input: InstrumentInput): Promise<InstrumentResponse> {
  const id = randomId();
  const now = new Date().toISOString();
  const statements = [
    db.prepare("INSERT INTO instrument(id,name,enabled,alert_mode,supports,resistances,high_water,fixed_drawdown,near_support_threshold,risk_reward_threshold,created_at,updated_at,rule_cycle_started_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)").bind(id, input.name, Number(input.enabled), input.alert_mode, JSON.stringify(input.supports), JSON.stringify(input.resistances), input.high_water, input.fixed_drawdown, input.near_support_threshold, input.risk_reward_threshold, now, now, now),
    ...input.source_mappings.map((source) => db.prepare("INSERT INTO source_mapping(id,instrument_id,provider,market_type,symbol,enabled) VALUES(?,?,?,?,?,?)").bind(randomId(), id, source.provider, source.market_type, source.symbol, Number(source.enabled))),
  ];
  await db.batch(statements);
  const row = await getInstrument(db, id);
  if (row === null) throw new Error("Created instrument missing");
  return instrumentResponse(db, row);
}

export async function replaceInstrument(db: D1Database, row: Instrument, input: InstrumentInput): Promise<InstrumentResponse> {
  const now = new Date().toISOString();
  const existingRows = await db.prepare("SELECT * FROM source_mapping WHERE instrument_id=?").bind(row.id).all<SourceMapping>();
  const existing = new Map(existingRows.results.map((source) => [`${source.provider}:${source.market_type}:${source.symbol}`, source]));
  const desired = new Set(input.source_mappings.map((source) => `${source.provider}:${source.market_type}:${source.symbol}`));
  const ruleFieldsChanged = row.alert_mode !== input.alert_mode || row.supports !== JSON.stringify(input.supports) || row.resistances !== JSON.stringify(input.resistances) || row.high_water !== input.high_water || row.fixed_drawdown !== input.fixed_drawdown || row.near_support_threshold !== input.near_support_threshold || row.risk_reward_threshold !== input.risk_reward_threshold;
  const statements: D1PreparedStatement[] = [];
  for (const source of input.source_mappings) {
    const current = existing.get(`${source.provider}:${source.market_type}:${source.symbol}`);
    if (current === undefined) statements.push(db.prepare("INSERT INTO source_mapping(id,instrument_id,provider,market_type,symbol,enabled) VALUES(?,?,?,?,?,?)").bind(randomId(), row.id, source.provider, source.market_type, source.symbol, Number(source.enabled)));
    else statements.push(db.prepare("UPDATE source_mapping SET enabled=? WHERE id=?").bind(Number(source.enabled), current.id));
  }
  for (const source of existingRows.results) {
    if (!desired.has(`${source.provider}:${source.market_type}:${source.symbol}`)) statements.push(db.prepare("DELETE FROM source_mapping WHERE id=?").bind(source.id));
  }
  if (ruleFieldsChanged) statements.push(db.prepare("DELETE FROM last_rule_state WHERE instrument_id=?").bind(row.id));
  statements.push(db.prepare("UPDATE instrument SET name=?,enabled=?,alert_mode=?,supports=?,resistances=?,high_water=?,fixed_drawdown=?,near_support_threshold=?,risk_reward_threshold=?,updated_at=?,rule_cycle_started_at=? WHERE id=?").bind(input.name, Number(input.enabled), input.alert_mode, JSON.stringify(input.supports), JSON.stringify(input.resistances), input.high_water, input.fixed_drawdown, input.near_support_threshold, input.risk_reward_threshold, now, now, row.id));
  await db.batch(statements);
  const updated = await getInstrument(db, row.id);
  if (updated === null) throw new Error("Updated instrument missing");
  return instrumentResponse(db, updated);
}

export async function patchInstrument(db: D1Database, row: Instrument, enabled: boolean): Promise<InstrumentResponse> {
  await db.prepare("UPDATE instrument SET enabled=?,updated_at=? WHERE id=?").bind(Number(enabled), new Date().toISOString(), row.id).run(); const updated = await getInstrument(db, row.id); if (updated === null) throw new Error("Updated instrument missing"); return instrumentResponse(db, updated);
}

export async function loadRuleState(db: D1Database, instrumentId: number, sourceId: number): Promise<RuleState | null> {
  return db.prepare("SELECT last_price,near_support_active,risk_reward_active,above_resistance_active,support_breach_active,near_support_last_alert_at,risk_reward_last_alert_at,breakout_last_alert_at,support_breach_last_alert_at,last_invalid_state FROM last_rule_state WHERE instrument_id=? AND source_mapping_id=?").bind(instrumentId, sourceId).first<RuleState>();
}
