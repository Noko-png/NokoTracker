const denominators = [2, 3, 4, 6, 8, 12];

export function normalizeFractionalQuantityValue(value: number) {
  return Number.isFinite(value) ? Number(value.toFixed(12)) : value;
}

export function formatFractionalQuantity(value: number) {
  if (!Number.isFinite(value)) return "";
  const normalized = normalizeFractionalQuantityValue(value);
  const absolute = Math.abs(normalized);
  const whole = Math.trunc(absolute);
  const fraction = absolute - whole;
  const sign = normalized < 0 ? "-" : "";
  if (Number.isInteger(normalized)) return String(normalized);
  for (const denominator of denominators) {
    const numerator = Math.round(fraction * denominator);
    // Only display actual fractions. Forms must preserve decimal quantities too.
    if (numerator > 0 && numerator < denominator && Math.abs(fraction - numerator / denominator) < 1e-12) {
      return whole === 0
        ? `${sign}${numerator}/${denominator}`
        : `${sign}${whole} ${numerator}/${denominator}`;
    }
  }
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 12, useGrouping: false }).format(normalized);
}

export function newBookingKey() {
  // getRandomValues also works on a local Home Assistant HTTP connection.
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
