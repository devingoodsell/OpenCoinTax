import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatCard, AllocationBar, StatCards } from "./RecentActivity";
import type { PortfolioStatsResponse, HoldingItem } from "../../api/client";

describe("StatCard", () => {
  it("renders label and formatted value", () => {
    render(<StatCard label="Income" value="1234.56" />);
    expect(screen.getByText("Income")).toBeInTheDocument();
    expect(screen.getByText("$1,234.56")).toBeInTheDocument();
  });

  it("applies success color for positive values", () => {
    const { container } = render(<StatCard label="Gains" value="100" />);
    const valueEl = container.querySelector(".text-lg");
    expect(valueEl?.getAttribute("style")).toContain("var(--success)");
  });

  it("applies danger color for negative values", () => {
    const { container } = render(<StatCard label="Loss" value="-50" />);
    const valueEl = container.querySelector(".text-lg");
    expect(valueEl?.getAttribute("style")).toContain("var(--danger)");
  });

  it("uses custom color when provided", () => {
    const { container } = render(<StatCard label="X" value="10" color="blue" />);
    const valueEl = container.querySelector(".text-lg");
    expect(valueEl?.getAttribute("style")).toContain("blue");
  });
});

describe("AllocationBar", () => {
  it("renders allocation segments", () => {
    const holdings: HoldingItem[] = [
      { asset_id: 1, asset_symbol: "BTC", asset_name: "Bitcoin", quantity: "1", market_value_usd: "50000", cost_basis_usd: "30000", unrealized_gain_usd: "20000", allocation_pct: "60" },
      { asset_id: 2, asset_symbol: "ETH", asset_name: "Ethereum", quantity: "10", market_value_usd: "30000", cost_basis_usd: "20000", unrealized_gain_usd: "10000", allocation_pct: "40" },
    ];
    render(<AllocationBar holdings={holdings} />);
    expect(screen.getByText("Asset Allocation")).toBeInTheDocument();
    expect(screen.getByText(/BTC 60%/)).toBeInTheDocument();
    expect(screen.getByText(/ETH 40%/)).toBeInTheDocument();
  });

  it("returns null for empty holdings", () => {
    const { container } = render(<AllocationBar holdings={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("StatCards", () => {
  it("renders all stat cards", () => {
    const stats: PortfolioStatsResponse = {
      total_in: "10000",
      total_out: "5000",
      total_income: "500",
      total_expenses: "200",
      total_fees: "100",
      realized_gains: "1000",
    };
    render(<StatCards stats={stats} />);
    expect(screen.getByText("In")).toBeInTheDocument();
    expect(screen.getByText("Out")).toBeInTheDocument();
    expect(screen.getByText("Income")).toBeInTheDocument();
    expect(screen.getByText("Expenses")).toBeInTheDocument();
    expect(screen.getByText("Trading Fees")).toBeInTheDocument();
    expect(screen.getByText("Realized Gains")).toBeInTheDocument();
  });
});
