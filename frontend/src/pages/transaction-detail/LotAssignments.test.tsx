import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LedgerTab, CostAnalysisTab } from "./LotAssignments";
import type { TxDetail } from "./TransactionInfo";

const BASE_TX: TxDetail = {
  id: 1,
  datetime_utc: "2024-06-15T14:30:00Z",
  type: "sell",
  from_amount: "0.5",
  from_asset_symbol: "BTC",
  to_amount: null,
  to_asset_symbol: null,
  fee_amount: null,
  fee_asset_symbol: null,
  fee_value_usd: null,
  from_value_usd: "30000",
  to_value_usd: null,
  net_value_usd: "30000",
  from_wallet_name: "Ledger",
  to_wallet_name: null,
  from_account_name: null,
  to_account_name: null,
  label: null,
  description: null,
  tx_hash: null,
  source: "csv_import",
  has_tax_error: false,
  tax_error: null,
  lot_assignments: [],
};

const TX_WITH_LOTS: TxDetail = {
  ...BASE_TX,
  lot_assignments: [
    { id: 1, amount: "0.3", cost_basis_usd: "9000.00", proceeds_usd: "18000.00", gain_loss_usd: "9000.00", holding_period: "long_term" },
    { id: 2, amount: "0.2", cost_basis_usd: "8000.00", proceeds_usd: "12000.00", gain_loss_usd: "4000.00", holding_period: "short_term" },
  ],
};

describe("LedgerTab", () => {
  it("shows empty message when no lot assignments", () => {
    render(<LedgerTab tx={BASE_TX} />);
    expect(screen.getByText("No lot assignments for this transaction type")).toBeInTheDocument();
  });

  it("renders lot assignment table with data", () => {
    render(<LedgerTab tx={TX_WITH_LOTS} />);
    expect(screen.getByText("Amount")).toBeInTheDocument();
    expect(screen.getByText("Cost Basis")).toBeInTheDocument();
    expect(screen.getByText("Proceeds")).toBeInTheDocument();
    expect(screen.getByText("Gain/Loss")).toBeInTheDocument();
    expect(screen.getByText("Long-term")).toBeInTheDocument();
    expect(screen.getByText("Short-term")).toBeInTheDocument();
  });
});

describe("CostAnalysisTab", () => {
  it("shows empty message when no lot assignments", () => {
    render(<CostAnalysisTab tx={BASE_TX} />);
    expect(screen.getByText("No cost analysis available for this transaction type")).toBeInTheDocument();
  });

  it("renders cost analysis with totals", () => {
    render(<CostAnalysisTab tx={TX_WITH_LOTS} />);
    expect(screen.getByText("Total Cost Basis")).toBeInTheDocument();
    expect(screen.getByText("Total Proceeds")).toBeInTheDocument();
    expect(screen.getByText("Total Realized Gain/Loss")).toBeInTheDocument();
    expect(screen.getByText("Holding Period Breakdown")).toBeInTheDocument();
  });
});
