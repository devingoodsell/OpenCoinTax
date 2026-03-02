import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../api/client", () => ({
  syncExchange: vi.fn(),
  createExchangeConnection: vi.fn(),
  deleteExchangeConnection: vi.fn(),
}));

import WalletImportSync from "./WalletCostBasis";
import { syncExchange, createExchangeConnection } from "../../api/client";

const mockSyncExchange = vi.mocked(syncExchange);
const mockCreateConnection = vi.mocked(createExchangeConnection);

const BASE_WALLET = {
  id: 1,
  name: "Coinbase",
  type: "exchange",
  category: "exchange" as const,
  provider: "coinbase",
  notes: null,
  is_archived: false,
  created_at: "2024-01-01",
  updated_at: "2024-01-01",
  total_cost_basis_usd: "5000",
  total_value_usd: "6000",
  accounts: [],
  balances: [],
  has_exchange_connection: false,
  exchange_last_synced_at: null,
};

describe("WalletImportSync", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders CSV import link", () => {
    render(
      <MemoryRouter>
        <WalletImportSync wallet={BASE_WALLET as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText("CSV Import")).toBeInTheDocument();
    expect(screen.getByText(/Go to CSV Import/)).toBeInTheDocument();
  });

  it("CSV import link points to correct URL", () => {
    render(
      <MemoryRouter>
        <WalletImportSync wallet={BASE_WALLET as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    const link = screen.getByText(/Go to CSV Import/);
    expect(link.getAttribute("href")).toBe("/import?wallet=1");
  });

  it("shows Connect API button when no connection", () => {
    render(
      <MemoryRouter>
        <WalletImportSync wallet={BASE_WALLET as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Connect API")).toBeInTheDocument();
    expect(screen.getByText(/Connect your exchange API/)).toBeInTheDocument();
  });

  it("shows Sync Now when connection exists", () => {
    const walletWithConn = { ...BASE_WALLET, has_exchange_connection: true, exchange_last_synced_at: null };
    render(
      <MemoryRouter>
        <WalletImportSync wallet={walletWithConn as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Sync Now")).toBeInTheDocument();
    expect(screen.getByText("Update Keys")).toBeInTheDocument();
    expect(screen.getByText("Remove")).toBeInTheDocument();
  });

  it("opens connection form on Connect API click", () => {
    render(
      <MemoryRouter>
        <WalletImportSync wallet={BASE_WALLET as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Connect API"));
    expect(screen.getByText("Exchange API Connection")).toBeInTheDocument();
    expect(screen.getByText("API Key")).toBeInTheDocument();
    expect(screen.getByText("API Secret")).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeInTheDocument();
  });

  it("shows last synced time", () => {
    const walletSynced = {
      ...BASE_WALLET,
      has_exchange_connection: true,
      exchange_last_synced_at: new Date(Date.now() - 120000).toISOString(),
    };
    render(
      <MemoryRouter>
        <WalletImportSync wallet={walletSynced as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Last synced/)).toBeInTheDocument();
  });

  it("syncs exchange and shows result", async () => {
    const walletWithConn = { ...BASE_WALLET, has_exchange_connection: true };
    mockSyncExchange.mockResolvedValue({
      data: { imported: 10, skipped: 3, errors: 0, error_messages: [] },
    } as any);
    const loadWallet = vi.fn();
    render(
      <MemoryRouter>
        <WalletImportSync wallet={walletWithConn as any} loadWallet={loadWallet} setError={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Sync Now"));
    await waitFor(() => {
      expect(mockSyncExchange).toHaveBeenCalledWith(1);
    });
    await waitFor(() => {
      expect(screen.getByText("Sync Complete")).toBeInTheDocument();
    });
    expect(screen.getByText(/10 imported/)).toBeInTheDocument();
    expect(screen.getByText(/3 skipped/)).toBeInTheDocument();
  });

  it("submits connection form", async () => {
    mockCreateConnection.mockResolvedValue({} as any);
    const loadWallet = vi.fn();
    render(
      <MemoryRouter>
        <WalletImportSync wallet={BASE_WALLET as any} loadWallet={loadWallet} setError={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Connect API"));
    const form = screen.getByText("Save").closest("form")!;
    const inputs = form.querySelectorAll("input[type='password']");
    fireEvent.change(inputs[0], { target: { value: "my-api-key" } });
    fireEvent.change(inputs[1], { target: { value: "my-api-secret" } });
    fireEvent.submit(form);
    await waitFor(() => {
      expect(mockCreateConnection).toHaveBeenCalledWith(1, expect.objectContaining({
        exchange_type: "coinbase",
        api_key: "my-api-key",
        api_secret: "my-api-secret",
      }));
    });
  });

  it("closes connection form on Cancel", () => {
    render(
      <MemoryRouter>
        <WalletImportSync wallet={BASE_WALLET as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Connect API"));
    expect(screen.getByText("Exchange API Connection")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByText("Exchange API Connection")).not.toBeInTheDocument();
  });

  it("opens connection form on Update Keys click", () => {
    const walletWithConn = { ...BASE_WALLET, has_exchange_connection: true };
    render(
      <MemoryRouter>
        <WalletImportSync wallet={walletWithConn as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Update Keys"));
    expect(screen.getByText("Exchange API Connection")).toBeInTheDocument();
  });

  it("shows sync error", async () => {
    const walletWithConn = { ...BASE_WALLET, has_exchange_connection: true };
    mockSyncExchange.mockRejectedValue({ response: { data: { detail: "API key expired" } } });
    render(
      <MemoryRouter>
        <WalletImportSync wallet={walletWithConn as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Sync Now"));
    await waitFor(() => {
      expect(screen.getByText("API key expired")).toBeInTheDocument();
    });
  });
});
