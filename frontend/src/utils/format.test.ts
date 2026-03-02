import { describe, it, expect } from "vitest";
import { formatCurrency, formatCrypto, formatNumber } from "./format";

describe("formatCurrency", () => {
  it("formats positive numbers with $ and commas", () => {
    expect(formatCurrency(12345.678)).toBe("$12,345.68");
  });

  it("formats negative numbers", () => {
    // toLocaleString puts negative sign after $
    expect(formatCurrency(-99.5)).toBe("$-99.50");
  });

  it("formats zero", () => {
    expect(formatCurrency(0)).toBe("$0.00");
  });

  it("parses strings", () => {
    expect(formatCurrency("1234.5")).toBe("$1,234.50");
  });

  it("returns empty for null/undefined/empty", () => {
    expect(formatCurrency(null)).toBe("");
    expect(formatCurrency(undefined)).toBe("");
    expect(formatCurrency("")).toBe("");
  });

  it("returns original string for NaN", () => {
    expect(formatCurrency("abc")).toBe("abc");
  });
});

describe("formatCrypto", () => {
  it("formats large amounts with 2 decimals", () => {
    expect(formatCrypto(1234.5678)).toBe("1,234.57");
  });

  it("formats medium amounts with 4 decimals", () => {
    expect(formatCrypto(1.23456789)).toBe("1.2346");
  });

  it("formats small amounts with 6 decimals", () => {
    expect(formatCrypto(0.00123456)).toBe("0.001235");
  });

  it("formats very small amounts with 4 significant digits", () => {
    expect(formatCrypto(0.00001234)).toBe("0.00001234");
  });

  it("formats zero", () => {
    expect(formatCrypto(0)).toBe("0");
  });

  it("handles negative values", () => {
    expect(formatCrypto(-5000)).toBe("-5,000");
  });

  it("parses strings", () => {
    expect(formatCrypto("42.12345")).toBe("42.1235");
  });

  it("returns empty for null/undefined/empty", () => {
    expect(formatCrypto(null)).toBe("");
    expect(formatCrypto(undefined)).toBe("");
    expect(formatCrypto("")).toBe("");
  });

  it("returns original string for NaN", () => {
    expect(formatCrypto("xyz")).toBe("xyz");
  });
});

describe("formatNumber", () => {
  it("formats with 2 decimal places by default", () => {
    expect(formatNumber(1234.5)).toBe("1,234.50");
  });

  it("formats with custom decimal places", () => {
    expect(formatNumber(1234.5678, 4)).toBe("1,234.5678");
  });

  it("parses strings", () => {
    expect(formatNumber("999.1")).toBe("999.10");
  });

  it("returns original string for NaN", () => {
    expect(formatNumber("bad")).toBe("bad");
  });
});
