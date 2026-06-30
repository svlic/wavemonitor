export function validateThreshold(value: string, name: string = "Threshold"): string | null {
  if (!value) return `${name} is required`;
  const num = Number(value);
  if (isNaN(num)) return `${name} must be a number`;
  if (num <= 0 || num >= 1) return `${name} must be between 0 and 1 (exclusive)`;
  return null;
}

export function validateRiskRewardThreshold(value: string): string | null {
  if (!value) return "Risk reward threshold is required";
  const num = Number(value);
  if (isNaN(num)) return "Risk reward threshold must be a number";
  if (num <= 0) return "Risk reward threshold must be greater than 0";
  return null;
}

export function validateSupportResistance(support: string, resistance: string): string | null {
  if (!support || !resistance) return "Both support and resistance are required";
  const s = Number(support);
  const r = Number(resistance);
  if (isNaN(s) || isNaN(r)) return "Support and resistance must be numbers";
  if (s <= 0 || r <= 0) return "Support and resistance must be positive";
  if (s >= r) return "Support must be strictly less than resistance";
  return null;
}
