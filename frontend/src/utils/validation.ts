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

export function validateSupportResistance(
  supports: readonly string[],
  resistances: readonly string[],
): string | null {
  const parsedSupports = supports.filter((value) => value.trim()).map(Number);
  const parsedResistances = resistances.filter((value) => value.trim()).map(Number);
  if (parsedSupports.length === 0 && parsedResistances.length === 0) {
    return "支撑位和阻力位至少填写一项";
  }
  if (parsedSupports.some((value) => !Number.isFinite(value))) return "支撑位必须是数字";
  if (parsedSupports.some((value) => value <= 0)) return "支撑位必须为正数";
  if (parsedResistances.some((value) => !Number.isFinite(value))) return "阻力位必须是数字";
  if (parsedResistances.some((value) => value <= 0)) return "阻力位必须为正数";
  if (
    parsedSupports.length > 0
    && parsedResistances.length > 0
    && Math.max(...parsedSupports) >= Math.min(...parsedResistances)
  ) {
    return parsedSupports.length === 1 && parsedResistances.length === 1
      ? "支撑位必须严格小于阻力位"
      : "所有支撑位必须严格小于所有阻力位";
  }
  return null;
}
