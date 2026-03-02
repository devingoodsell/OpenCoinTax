import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../api/client", () => ({
  fetchTransactions: vi.fn(),
  fetchTransactionErrorCount: vi.fn(),
  fetchWallets: vi.fn(),
}));

import Transactions from "./Transactions";
import { fetchTransactions, fetchTransactionErrorCount, fetchWallets } from "../../api/client";

const mockFetchTxns = vi.mocked(fetchTransactions);
const mockFetchErrorCount = vi.mocked(fetchTransactionErrorCount);
const mockFetchWallets = vi.mocked(fetchWallets);

const MOCK_TX = {
  id: 1,
  datetime_utc: "2024-06-15T14:30:00Z",
  type: "buy",
  from_amount: "1000",
  from_asset_symbol: "USD",
  from_wallet_name: "Coinbase",
  from_account_name: null,
  to_amount: "0.015",
  to_asset_symbol: "BTC",
  to_wallet_name: "Coinbase",
  to_account_name: null,
  fee_amount: null,
  fee_asset_symbol: null,
  net_value_usd: "1000",
  from_value_usd: "1000",
  to_value_usd: "1000",
  label: null,
  description: null,
  tx_hash: null,
  has_tax_error: false,
  tax_error: null,
};

describe("Transactions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchWallets.mockResolvedValue({ data: [] } as any);
    mockFetchErrorCount.mockResolvedValue({ data: { error_count: 0 } } as any);
  });

  it("shows loading spinner initially", () => {
    mockFetchTxns.mockReturnValue(new Promise(() => {}) as any);
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders empty state when no transactions", async () => {
    mockFetchTxns.mockResolvedValue({
      data: { items: [], total: 0 },
    } as any);
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("No transactions")).toBeInTheDocument();
    });
  });

  it("renders transactions when data loads", async () => {
    mockFetchTxns.mockResolvedValue({
      data: { items: [MOCK_TX], total: 1 },
    } as any);
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Buy")).toBeInTheDocument();
    });
  });

  it("shows error banner on failure", async () => {
    mockFetchTxns.mockRejectedValue({
      response: { data: { detail: "Server error" } },
    });
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Server error")).toBeInTheDocument();
    });
  });

  it("renders type toggle pills", async () => {
    mockFetchTxns.mockResolvedValue({ data: { items: [MOCK_TX], total: 1 } } as any);
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Buy"));
    expect(screen.getByText("Sell")).toBeInTheDocument();
    expect(screen.getByText("Trade")).toBeInTheDocument();
    expect(screen.getByText("Transfer")).toBeInTheDocument();
    expect(screen.getByText("Deposit")).toBeInTheDocument();
    expect(screen.getByText("Withdrawal")).toBeInTheDocument();
  });

  it("shows Import link", async () => {
    mockFetchTxns.mockResolvedValue({ data: { items: [MOCK_TX], total: 1 } } as any);
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Buy"));
    expect(screen.getByText("Import")).toBeInTheDocument();
  });

  it("shows total count in header", async () => {
    mockFetchTxns.mockResolvedValue({
      data: { items: [MOCK_TX], total: 42 },
    } as any);
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("(42)")).toBeInTheDocument();
    });
  });

  it("renders wallet filter dropdown", async () => {
    mockFetchWallets.mockResolvedValue({
      data: [{ id: 1, name: "Coinbase" }, { id: 2, name: "Ledger" }],
    } as any);
    mockFetchTxns.mockResolvedValue({ data: { items: [MOCK_TX], total: 1 } } as any);
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Buy"));
    expect(screen.getByText("All wallets")).toBeInTheDocument();
  });

  it("shows errors button when there are tax errors", async () => {
    mockFetchErrorCount.mockResolvedValue({ data: { error_count: 3 } } as any);
    mockFetchTxns.mockResolvedValue({ data: { items: [MOCK_TX], total: 1 } } as any);
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Errors (3)")).toBeInTheDocument();
    });
  });

  it("renders date filter inputs", async () => {
    mockFetchTxns.mockResolvedValue({ data: { items: [MOCK_TX], total: 1 } } as any);
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Buy"));
    expect(screen.getByTitle("From date")).toBeInTheDocument();
    expect(screen.getByTitle("To date")).toBeInTheDocument();
  });

  it("renders search input", async () => {
    mockFetchTxns.mockResolvedValue({ data: { items: [MOCK_TX], total: 1 } } as any);
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Buy"));
    expect(screen.getByPlaceholderText("Search tx hash or description...")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Token (e.g. ETH, BTC)...")).toBeInTheDocument();
  });

  it("groups transactions by date", async () => {
    mockFetchTxns.mockResolvedValue({
      data: {
        items: [
          { ...MOCK_TX, id: 1, datetime_utc: "2024-06-15T14:30:00Z" },
          { ...MOCK_TX, id: 2, datetime_utc: "2024-06-15T10:00:00Z" },
        ],
        total: 2,
      },
    } as any);
    render(
      <MemoryRouter>
        <Transactions />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Jun 15, 2024")).toBeInTheDocument();
    });
  });
});
