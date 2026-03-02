import { describe, it, expect, vi } from "vitest";

// Mock window.open to prevent actual window creation
const mockOpen = vi.fn().mockReturnValue({
  document: {
    write: vi.fn(),
    close: vi.fn(),
  },
  focus: vi.fn(),
  print: vi.fn(),
});
vi.stubGlobal("open", mockOpen);

import { openPrintWindow } from "./PrintReport";

describe("openPrintWindow", () => {
  it("is a function", () => {
    expect(typeof openPrintWindow).toBe("function");
  });

  it("opens a new window with print content", () => {
    // openPrintWindow(taxYear, f8949, schedD, summary) — 4 args
    const f8949 = {
      short_term_rows: [
        {
          description: "0.5 BTC",
          date_acquired: "2024-01-01",
          date_sold: "2024-06-01",
          proceeds: "25000.00",
          cost_basis: "20000.00",
          gain_loss: "5000.00",
          checkbox_category: "A",
        },
      ],
      long_term_rows: [],
      short_term_totals: { proceeds: "25000", cost_basis: "20000", gain_loss: "5000" },
      long_term_totals: null,
    };
    const schedD = {
      lines: [],
      net_short_term: "5000",
      net_long_term: "0",
      combined_net: "5000",
    };
    const summary = {
      total_proceeds: "25000",
      total_cost_basis: "20000",
      short_term_gains: "5000",
      short_term_losses: "0",
      long_term_gains: "0",
      long_term_losses: "0",
      net_gain_loss: "5000",
      staking_income: "0",
      airdrop_income: "0",
      fork_income: "0",
      mining_income: "0",
      interest_income: "0",
      other_income: "0",
      total_income: "0",
      total_cost_expenses: "0",
      transfer_fees: "0",
      total_fees_usd: "0",
      eoy_balances: [],
    };
    openPrintWindow(2025, f8949, schedD, summary);
    expect(mockOpen).toHaveBeenCalled();
  });
});
