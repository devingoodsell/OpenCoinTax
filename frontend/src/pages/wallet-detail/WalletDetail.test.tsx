import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../../api/client", () => ({
  fetchWallet: vi.fn(),
  updateWallet: vi.fn(),
  fetchWalletAccounts: vi.fn(),
  fetchWalletTransactions: vi.fn(),
  createAccount: vi.fn(),
  deleteAccount: vi.fn(),
  syncAccount: vi.fn(),
  fetchWalletHoldings: vi.fn(),
  refreshCurrentPrices: vi.fn(),
  hideAsset: vi.fn(),
  unhideAsset: vi.fn(),
  fetchWalletCostBasis: vi.fn(),
  uploadCsv: vi.fn(),
  confirmImport: vi.fn(),
}));

import WalletDetail from "./WalletDetail";
import { fetchWallet } from "../../api/client";

const mockFetchWallet = vi.mocked(fetchWallet);

function renderWithRoute(walletId: string) {
  return render(
    <MemoryRouter initialEntries={[`/wallets/${walletId}`]}>
      <Routes>
        <Route path="/wallets/:id" element={<WalletDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WalletDetail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading spinner initially", () => {
    mockFetchWallet.mockReturnValue(new Promise(() => {}) as any);
    renderWithRoute("1");
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders wallet detail after loading", async () => {
    mockFetchWallet.mockResolvedValue({
      data: {
        id: 1,
        name: "My Ledger",
        type: "hardware",
        category: "wallet",
        provider: "ledger",
        notes: "Test notes",
        is_archived: false,
        created_at: "2024-01-01",
        updated_at: "2024-01-01",
        accounts: [],
        transaction_summary: { total: 0, by_type: {} },
      },
    } as any);
    renderWithRoute("1");
    await waitFor(() => {
      expect(screen.getByText("My Ledger")).toBeInTheDocument();
    });
    expect(screen.getByText("Wallet")).toBeInTheDocument();
  });

  it("shows error on fetch failure", async () => {
    mockFetchWallet.mockRejectedValue({
      response: { data: { detail: "Wallet not found" } },
    });
    renderWithRoute("999");
    await waitFor(() => {
      expect(screen.getByText("Wallet not found")).toBeInTheDocument();
    });
  });

  it("shows notes section", async () => {
    mockFetchWallet.mockResolvedValue({
      data: {
        id: 1,
        name: "Exchange",
        type: "exchange",
        category: "exchange",
        provider: null,
        notes: "My exchange notes",
        is_archived: false,
        created_at: "2024-01-01",
        updated_at: "2024-01-01",
        accounts: [{ id: 1, name: "BTC", address: "bc1...", blockchain: "bitcoin" }],
        transaction_summary: { total: 5, by_type: { buy: 3, sell: 2 } },
      },
    } as any);
    renderWithRoute("1");
    await waitFor(() => {
      expect(screen.getByText("Notes")).toBeInTheDocument();
    });
    expect(screen.getByText("My exchange notes")).toBeInTheDocument();
  });
});
