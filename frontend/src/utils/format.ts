/**
 * Format a value as USD currency: "$12,345.67"
 * Accepts strings, numbers, or null. Returns empty string for null/undefined.
 */
export function formatCurrency(val: string | number | null | undefined): string {
  if (val === null || val === undefined || val === "") return "";
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(n)) return String(val);
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * Format a crypto amount with dynamic decimal places based on magnitude.
 * - >= 1000: 2 decimals (e.g., "1,234.56")
 * - >= 1: 4 decimals (e.g., "1.2345")
 * - >= 0.0001: 6 decimals (e.g., "0.001234")
 * - < 0.0001: 4 significant digits (e.g., "0.00001234")
 */
export function formatCrypto(val: string | number | null | undefined): string {
  if (val === null || val === undefined || val === "") return "";
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(n)) return String(val);
  if (n === 0) return "0";
  const abs = Math.abs(n);
  if (abs >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (abs >= 1) return n.toLocaleString("en-US", { maximumFractionDigits: 4 });
  if (abs >= 0.0001) return n.toLocaleString("en-US", { maximumFractionDigits: 6 });
  return n.toPrecision(4);
}

/**
 * Format a numeric value with fixed decimal places and commas: "12,345.67"
 * Used primarily in reports for consistent number display.
 */
export function formatNumber(val: string | number, decimals = 2): string {
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(n)) return String(val);
  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}
