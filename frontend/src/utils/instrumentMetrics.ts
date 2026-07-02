function parsePositiveDecimal(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

/** (price - support) / price × 100 — same basis as backend near_support_metric. */
export function computeSupportDistancePercent(price: string, support: string): number | null {
  const priceN = parsePositiveDecimal(price);
  const supportN = parsePositiveDecimal(support);
  if (priceN === null || supportN === null || priceN <= supportN) {
    return null;
  }
  return ((priceN - supportN) / priceN) * 100;
}

/** (resistance - price) / price × 100 — upside room to resistance. */
export function computeResistanceDistancePercent(price: string, resistance: string): number | null {
  const priceN = parsePositiveDecimal(price);
  const resistanceN = parsePositiveDecimal(resistance);
  if (priceN === null || resistanceN === null || priceN >= resistanceN) {
    return null;
  }
  return ((resistanceN - priceN) / priceN) * 100;
}

/** (resistance - price) / (price - support) — matches backend risk_reward_ratio. */
export function computeRiskRewardRatio(
  price: string,
  support: string,
  resistance: string,
): number | null {
  const priceN = parsePositiveDecimal(price);
  const supportN = parsePositiveDecimal(support);
  const resistanceN = parsePositiveDecimal(resistance);
  if (priceN === null || supportN === null || resistanceN === null) {
    return null;
  }
  if (priceN <= supportN || priceN >= resistanceN) {
    return null;
  }
  const denominator = priceN - supportN;
  if (denominator <= 0) {
    return null;
  }
  return (resistanceN - priceN) / denominator;
}

export function formatMetricPercent(value: number | null, fractionDigits = 2): string {
  if (value === null) {
    return "—";
  }
  return `${value.toFixed(fractionDigits)}%`;
}

export function formatRiskReward(value: number | null, fractionDigits = 2): string {
  if (value === null) {
    return "—";
  }
  return value.toFixed(fractionDigits);
}