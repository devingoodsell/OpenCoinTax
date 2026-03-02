import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { getTypeConfig, formatAmount, formatUsd, TypeBadge } from "./transactionHelpers";

describe("getTypeConfig", () => {
  it("returns config for known types", () => {
    const buy = getTypeConfig("buy");
    expect(buy.label).toBe("Buy");
    expect(buy.color).toBeTruthy();

    const sell = getTypeConfig("sell");
    expect(sell.label).toBe("Sell");
  });

  it("returns default config for unknown type", () => {
    const cfg = getTypeConfig("unknown_type");
    expect(cfg.label).toBe("unknown_type");
    expect(cfg.icon).toBe("\u2022");
  });
});

describe("formatAmount (re-exported formatCrypto)", () => {
  it("formats crypto amounts", () => {
    expect(formatAmount(1234.56)).toBe("1,234.56");
    expect(formatAmount(0.001234)).toBe("0.001234");
  });
});

describe("formatUsd (re-exported formatCurrency)", () => {
  it("formats USD amounts", () => {
    expect(formatUsd(1234.5)).toBe("$1,234.50");
  });
});

describe("TypeBadge", () => {
  it("renders with correct icon", () => {
    const { container } = render(<TypeBadge type="buy" />);
    expect(container.textContent).toContain("\u2193");
  });

  it("renders unknown type", () => {
    const { container } = render(<TypeBadge type="other" />);
    expect(container.textContent).toContain("\u2022");
  });
});
