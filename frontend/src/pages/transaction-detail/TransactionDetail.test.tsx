import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../../api/client", () => ({
  fetchTransaction: vi.fn(),
  deleteTransaction: vi.fn(),
  updateTransaction: vi.fn(),
}));

import TransactionDetail from "./TransactionDetail";
import { fetchTransaction } from "../../api/client";

const mockFetchTx = vi.mocked(fetchTransaction);

function renderWithRoute(txId: string) {
  return render(
    <MemoryRouter initialEntries={[`/transactions/${txId}`]}>
      <Routes>
        <Route path="/transactions/:id" element={<TransactionDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

// TxDetail requires: source, fee_value_usd, lot_assignments
const MOCK_TX = {
  id: 1,
  datetime_utc: "2024-06-15T14:30:00Z",
  type: "buy",
  from_amount: "1000.00",
  from_asset_symbol: "USD",
  to_amount: "0.015",
  to_asset_symbol: "BTC",
  fee_amount: "5.00",
  fee_asset_symbol: "USD",
  fee_value_usd: "5.00",
  net_value_usd: "1000.00",
  from_value_usd: "1000.00",
  to_value_usd: "1000.00",
  label: null,
  description: "Buy BTC",
  tx_hash: "0xabc123",
  has_tax_error: false,
  tax_error: null,
  from_wallet_name: "Coinbase",
  to_wallet_name: "Coinbase",
  from_account_name: null,
  to_account_name: null,
  source: "csv_import",
  lot_assignments: [],
};

describe("TransactionDetail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading spinner initially", () => {
    mockFetchTx.mockReturnValue(new Promise(() => {}) as any);
    renderWithRoute("1");
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders transaction detail after loading", async () => {
    mockFetchTx.mockResolvedValue({ data: MOCK_TX } as any);
    renderWithRoute("1");
    await waitFor(() => {
      expect(screen.getByText("Buy")).toBeInTheDocument();
    });
  });

  it("shows error on fetch failure", async () => {
    mockFetchTx.mockRejectedValue({
      response: { data: { detail: "Not found" } },
    });
    renderWithRoute("999");
    await waitFor(() => {
      expect(screen.getByText("Not found")).toBeInTheDocument();
    });
  });

  it("shows tax error banner when present", async () => {
    mockFetchTx.mockResolvedValue({
      data: { ...MOCK_TX, has_tax_error: true, tax_error: "Missing cost basis" },
    } as any);
    renderWithRoute("1");
    await waitFor(() => {
      expect(screen.getByText("Tax Calculation Error")).toBeInTheDocument();
    });
    expect(screen.getByText("Missing cost basis")).toBeInTheDocument();
  });
});
