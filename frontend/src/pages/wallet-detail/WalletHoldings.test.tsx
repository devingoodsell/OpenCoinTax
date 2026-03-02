import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("../../api/client", () => ({
  refreshCurrentPrices: vi.fn(),
  hideAsset: vi.fn(),
}));

import WalletHoldings from "./WalletHoldings";

const EMPTY_WALLET = {
  id: 1,
  name: "Ledger",
  type: "hardware",
  category: "wallet",
  provider: null,
  notes: null,
  is_archived: false,
  created_at: "2024-01-01",
  updated_at: "2024-01-01",
  total_cost_basis_usd: "0",
  total_value_usd: "0",
  accounts: [],
  balances: [],
  has_exchange_connection: false,
  exchange_last_synced_at: null,
};

const WALLET_WITH_BALANCES = {
  ...EMPTY_WALLET,
  balances: [
    {
      symbol: "BTC",
      asset_id: 1,
      quantity: "0.5",
      cost_basis_usd: "15000.00",
      current_price_usd: "65000.00",
      market_value_usd: "32500.00",
      roi_pct: "116.67",
    },
    {
      symbol: "ETH",
      asset_id: 2,
      quantity: "10",
      cost_basis_usd: "20000.00",
      current_price_usd: null,
      market_value_usd: null,
      roi_pct: null,
    },
  ],
};

describe("WalletHoldings", () => {
  it("shows empty message when no holdings", () => {
    render(
      <WalletHoldings wallet={EMPTY_WALLET as any} setWallet={vi.fn()} setError={vi.fn()} loadWallet={vi.fn()} />,
    );
    expect(screen.getByText(/No holdings found/)).toBeInTheDocument();
  });

  it("renders holdings table", () => {
    render(
      <WalletHoldings wallet={WALLET_WITH_BALANCES as any} setWallet={vi.fn()} setError={vi.fn()} loadWallet={vi.fn()} />,
    );
    expect(screen.getByText("Holdings")).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.getByText("ETH")).toBeInTheDocument();
    expect(screen.getByText("Refresh Prices")).toBeInTheDocument();
  });

  it("renders ROI values", () => {
    render(
      <WalletHoldings wallet={WALLET_WITH_BALANCES as any} setWallet={vi.fn()} setError={vi.fn()} loadWallet={vi.fn()} />,
    );
    expect(screen.getByText("+116.67%")).toBeInTheDocument();
  });

  it("shows hide buttons", () => {
    render(
      <WalletHoldings wallet={WALLET_WITH_BALANCES as any} setWallet={vi.fn()} setError={vi.fn()} loadWallet={vi.fn()} />,
    );
    const hideButtons = screen.getAllByText("Hide");
    expect(hideButtons.length).toBe(2);
  });
});
