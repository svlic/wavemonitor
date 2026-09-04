import Decimal from "decimal.js";
import type { AlertDecision, AlertKind, RuleState } from "./types";

Decimal.set({ precision: 40, rounding: Decimal.ROUND_HALF_EVEN });
const ZERO = new Decimal(0);

export function decimal(value: string): Decimal {
  const parsed = new Decimal(value);
  if (!parsed.isFinite()) throw new Error("Decimal value must be finite");
  return parsed;
}

export function fixed(value: Decimal | string): string {
  return (typeof value === "string" ? decimal(value) : value).toFixed(10);
}

export function nearestPair(supports: string[], resistances: string[], priceText: string): [string | null, string | null] {
  const price = decimal(priceText);
  const below = supports.map(decimal).filter((level) => level.lt(price));
  const above = resistances.map(decimal).filter((level) => level.gt(price));
  const support = below.length === 0 ? null : Decimal.max(...below);
  const resistance = above.length === 0 ? null : Decimal.min(...above);
  return [support === null ? null : fixed(support), resistance === null ? null : fixed(resistance)];
}

export interface RuleEvaluation {
  alerts: AlertDecision[];
  nextState: RuleState;
  invalidState: string | null;
}

function alert(kind: AlertKind, price: Decimal, support: Decimal, resistance: Decimal, threshold: Decimal | null, metric: Decimal, at: string, message: string): AlertDecision {
  return { kind, price: fixed(price), support: fixed(support), resistance: fixed(resistance), threshold: threshold === null ? null : fixed(threshold), metric: metric.toString(), triggered_at: at, message };
}

export function emptyRuleState(): RuleState {
  return { last_price: null, near_support_active: 0, risk_reward_active: 0, above_resistance_active: 0, support_breach_active: 0, near_support_last_alert_at: null, risk_reward_last_alert_at: null, breakout_last_alert_at: null, support_breach_last_alert_at: null, last_invalid_state: null };
}

export function evaluateRules(args: { price: string; support: string | null; resistance: string | null; nearSupportThreshold: string | null; riskRewardThreshold: string | null; previous: RuleState; observedAt: string }): RuleEvaluation {
  const price = decimal(args.price);
  const support = args.support === null ? null : decimal(args.support);
  const resistance = args.resistance === null ? null : decimal(args.resistance);
  const nearThreshold = args.nearSupportThreshold === null ? null : decimal(args.nearSupportThreshold);
  const riskThreshold = args.riskRewardThreshold === null ? null : decimal(args.riskRewardThreshold);
  if (support !== null && nearThreshold === null) throw new Error("near_support_threshold is required when support is set");
  if (support !== null && resistance !== null && riskThreshold === null) throw new Error("risk_reward_threshold is required when support and resistance are set");
  const snapshotSupport = support ?? price;
  const snapshotResistance = resistance ?? price;
  const alerts: AlertDecision[] = [];

  if (support !== null && price.lte(support)) {
    if (args.previous.support_breach_last_alert_at === null) alerts.push(alert("support_breach", price, snapshotSupport, snapshotResistance, support, price, args.observedAt, `price ${price} breached support ${support}`));
    return { alerts, invalidState: "price_not_above_support", nextState: { ...emptyRuleState(), last_price: fixed(price), support_breach_active: 1, support_breach_last_alert_at: alerts.length > 0 ? args.observedAt : args.previous.support_breach_last_alert_at, last_invalid_state: "price_not_above_support" } };
  }

  let nearActive = false;
  if (support !== null && nearThreshold !== null) {
    const metric = price.minus(support).div(price);
    nearActive = metric.lte(nearThreshold);
    if (nearActive && args.previous.near_support_last_alert_at === null) alerts.push(alert("near_support", price, snapshotSupport, snapshotResistance, nearThreshold, metric, args.observedAt, `price ${price} is within ${metric} of support ${support}`));
  }
  let riskActive = false;
  if (support !== null && resistance !== null && riskThreshold !== null && price.lt(resistance)) {
    const metric = resistance.minus(price).div(price.minus(support));
    riskActive = metric.gte(riskThreshold);
    if (riskActive && args.previous.risk_reward_last_alert_at === null) alerts.push(alert("risk_reward", price, snapshotSupport, snapshotResistance, riskThreshold, metric, args.observedAt, `risk/reward ${metric} reached threshold ${riskThreshold} at price ${price}`));
  }
  const above = resistance !== null && price.gt(resistance);
  const previousPrice = args.previous.last_price === null ? null : decimal(args.previous.last_price);
  const crossed = above && previousPrice !== null && previousPrice.lte(resistance!);
  if (crossed && args.previous.breakout_last_alert_at === null) alerts.push(alert("resistance_breakout", price, snapshotSupport, snapshotResistance, resistance, price, args.observedAt, `price ${price} crossed resistance ${resistance}`));
  const stamp = (kind: AlertKind, active: boolean, previous: string | null): string | null => active ? (alerts.find((item) => item.kind === kind)?.triggered_at ?? previous) : null;
  return { alerts, invalidState: null, nextState: { last_price: fixed(price), near_support_active: Number(nearActive), risk_reward_active: Number(riskActive), above_resistance_active: Number(above), support_breach_active: 0, near_support_last_alert_at: stamp("near_support", nearActive, args.previous.near_support_last_alert_at), risk_reward_last_alert_at: stamp("risk_reward", riskActive, args.previous.risk_reward_last_alert_at), breakout_last_alert_at: stamp("resistance_breakout", above, args.previous.breakout_last_alert_at), support_breach_last_alert_at: null, last_invalid_state: null } };
}
