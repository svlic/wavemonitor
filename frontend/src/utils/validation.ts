export function validateThreshold(value: string, name: string = "阈值"): string | null {
  if (!value) return `${name}不能为空`;
  const num = Number(value);
  if (isNaN(num)) return `${name}必须是数字`;
  if (num <= 0 || num >= 1) return `${name}必须介于 0 和 1 之间（不含边界）`;
  return null;
}

export function validateRiskRewardThreshold(value: string): string | null {
  if (!value) return "风险回报阈值不能为空";
  const num = Number(value);
  if (isNaN(num)) return "风险回报阈值必须是数字";
  if (num <= 0) return "风险回报阈值必须大于 0";
  return null;
}

export function validateSupportResistance(support: string, resistance: string): string | null {
  if (!support || !resistance) return "支撑位和阻力位都不能为空";
  const s = Number(support);
  const r = Number(resistance);
  if (isNaN(s) || isNaN(r)) return "支撑位和阻力位必须是数字";
  if (s <= 0 || r <= 0) return "支撑位和阻力位必须为正数";
  if (s >= r) return "支撑位必须严格小于阻力位";
  return null;
}
