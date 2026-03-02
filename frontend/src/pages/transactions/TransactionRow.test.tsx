import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TransactionCard, { type Transaction } from "./TransactionRow";

const MOCK_TX: Transaction = {
  id: 1,
  datetime_utc: "2024-06-15T14:30:00Z",
  type: "buy",
  from_amount: "1000.00",
  from_asset_symbol: "USD",
  from_wallet_name: "Coinbase",
  from_account_name: null,
  to_amount: "0.015",
  to_asset_symbol: "BTC",
  to_wallet_name: "Coinbase",
  to_account_name: null,
  fee_amount: "5.00",
  fee_asset_symbol: "USD",
  net_value_usd: "1000.00",
  from_value_usd: "1000.00",
  to_value_usd: "1000.00",
  label: null,
  description: "Buy BTC with USD",
  tx_hash: "0xabc123def456",
  has_tax_error: false,
  tax_error: null,
};

describe("TransactionCard", () => {
  it("renders transaction type badge and info", () => {
    render(
      <MemoryRouter>
        <TransactionCard tx={MOCK_TX} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Buy")).toBeInTheDocument();
  });

  it("renders USD value", () => {
    render(
      <MemoryRouter>
        <TransactionCard tx={MOCK_TX} />
      </MemoryRouter>,
    );
    expect(screen.getByText("$1,000.00")).toBeInTheDocument();
  });

  it("expands on click to show details", () => {
    render(
      <MemoryRouter>
        <TransactionCard tx={MOCK_TX} />
      </MemoryRouter>,
    );
    // The clickable div has class cursor-pointer
    const card = screen.getByText("Buy").closest("div.cursor-pointer")!;
    fireEvent.click(card);
    // After expansion, the ExpandedDetail shows "View full details →"
    expect(screen.getByText(/View full details/)).toBeInTheDocument();
  });

  it("shows tax error indicator when has_tax_error", () => {
    const errorTx = { ...MOCK_TX, has_tax_error: true, tax_error: "Missing cost basis" };
    render(
      <MemoryRouter>
        <TransactionCard tx={errorTx} />
      </MemoryRouter>,
    );
    // The component renders a red dot with title attribute, not text
    const indicator = screen.getByTitle("Missing cost basis");
    expect(indicator).toBeInTheDocument();
  });

  it("shows fee when expanded", () => {
    render(
      <MemoryRouter>
        <TransactionCard tx={MOCK_TX} />
      </MemoryRouter>,
    );
    const card = screen.getByText("Buy").closest("div.cursor-pointer")!;
    fireEvent.click(card);
    expect(screen.getByText("Fee")).toBeInTheDocument();
  });
});
