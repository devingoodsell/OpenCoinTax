import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../api/client", () => ({
  createAccount: vi.fn(),
  updateAccount: vi.fn(),
  deleteAccount: vi.fn(),
  syncAccount: vi.fn(),
  fetchWallets: vi.fn(),
}));

import WalletAccounts from "./WalletAccounts";
import { createAccount, updateAccount, syncAccount, fetchWallets } from "../../api/client";

const mockCreateAccount = vi.mocked(createAccount);
const mockUpdateAccount = vi.mocked(updateAccount);
const mockSyncAccount = vi.mocked(syncAccount);
const mockFetchWallets = vi.mocked(fetchWallets);

const EMPTY_WALLET = {
  id: 1,
  name: "Ledger",
  type: "hardware",
  category: "wallet" as const,
  provider: "ledger",
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

const WALLET_WITH_ACCOUNTS = {
  ...EMPTY_WALLET,
  accounts: [
    {
      id: 10,
      name: "BTC Main",
      blockchain: "bitcoin",
      address: "bc1q0000000000000000000000000000000000",
      is_archived: false,
      last_synced_at: null,
    },
    {
      id: 11,
      name: "ETH Main",
      blockchain: "ethereum",
      address: "0x1234567890abcdef1234567890abcdef12345678",
      is_archived: false,
      last_synced_at: new Date(Date.now() - 300000).toISOString(),
    },
  ],
};

/**
 * Get all DropdownMenu trigger buttons (SVG buttons with no text).
 * Each account row has a "Sync" button (with text) and a dropdown trigger (SVG, no text).
 * The "Add Account" / "Cancel" button also has text.
 */
function getDropdownTriggers() {
  const allButtons = screen.getAllByRole("button");
  return allButtons.filter((b) => {
    const text = b.textContent?.trim() ?? "";
    // Dropdown triggers have no readable text (only SVG content)
    return text === "" || text === "";
  });
}

describe("WalletAccounts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows empty state when no accounts", () => {
    render(
      <MemoryRouter>
        <WalletAccounts wallet={EMPTY_WALLET as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/No accounts yet/)).toBeInTheDocument();
  });

  it("renders accounts list", () => {
    render(
      <MemoryRouter>
        <WalletAccounts wallet={WALLET_WITH_ACCOUNTS as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText("BTC Main")).toBeInTheDocument();
    expect(screen.getByText("ETH Main")).toBeInTheDocument();
    expect(screen.getByText("Bitcoin")).toBeInTheDocument();
    expect(screen.getByText("Ethereum")).toBeInTheDocument();
  });

  it("shows Add Account button and form", () => {
    render(
      <MemoryRouter>
        <WalletAccounts wallet={EMPTY_WALLET as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Add Account"));
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Blockchain")).toBeInTheDocument();
    expect(screen.getByText("Address")).toBeInTheDocument();
  });

  it("renders sync buttons for each account", () => {
    render(
      <MemoryRouter>
        <WalletAccounts wallet={WALLET_WITH_ACCOUNTS as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    const syncButtons = screen.getAllByText("Sync");
    expect(syncButtons.length).toBe(2);
  });

  it("shows synced time for synced accounts", () => {
    render(
      <MemoryRouter>
        <WalletAccounts wallet={WALLET_WITH_ACCOUNTS as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Synced/)).toBeInTheDocument();
  });

  it("submits create account form", async () => {
    mockCreateAccount.mockResolvedValue({} as any);
    const loadWallet = vi.fn();
    render(
      <MemoryRouter>
        <WalletAccounts wallet={EMPTY_WALLET as any} loadWallet={loadWallet} setError={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Add Account"));
    fireEvent.change(screen.getByPlaceholderText("My BTC"), { target: { value: "Test Account" } });
    fireEvent.change(screen.getByPlaceholderText("bc1q..."), { target: { value: "0x1234567890abcdef1234567890abcdef12345678" } });
    // Find the submit button (text "Add Account" when form is open, but it's now the submit button)
    const submitBtn = screen.getAllByRole("button").find(b => b.textContent === "Add Account" && b.getAttribute("type") === "submit");
    fireEvent.click(submitBtn!);
    await waitFor(() => {
      expect(mockCreateAccount).toHaveBeenCalledWith(1, expect.objectContaining({
        name: "Test Account",
        address: "0x1234567890abcdef1234567890abcdef12345678",
      }));
    });
  });

  it("detects ethereum blockchain from address", () => {
    render(
      <MemoryRouter>
        <WalletAccounts wallet={EMPTY_WALLET as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Add Account"));
    const addressInput = screen.getByPlaceholderText("bc1q...");
    fireEvent.change(addressInput, { target: { value: "0x1234567890abcdef1234567890abcdef12345678" } });
    // The blockchain select should auto-detect ethereum
    const blockchainSelect = screen.getByDisplayValue("Ethereum");
    expect(blockchainSelect).toBeInTheDocument();
  });

  it("syncs an account", async () => {
    mockSyncAccount.mockResolvedValue({ data: { imported: 5, skipped: 2, errors: 0, error_messages: [] } } as any);
    const loadWallet = vi.fn();
    render(
      <MemoryRouter>
        <WalletAccounts wallet={WALLET_WITH_ACCOUNTS as any} loadWallet={loadWallet} setError={vi.fn()} />
      </MemoryRouter>,
    );
    const syncButtons = screen.getAllByText("Sync");
    fireEvent.click(syncButtons[0]);
    await waitFor(() => {
      expect(mockSyncAccount).toHaveBeenCalledWith(1, 10);
    });
    await waitFor(() => {
      expect(screen.getByText("Sync Complete")).toBeInTheDocument();
    });
    expect(screen.getByText(/5 imported/)).toBeInTheDocument();
    expect(screen.getByText(/2 skipped/)).toBeInTheDocument();
  });

  it("opens rename form from dropdown", async () => {
    render(
      <MemoryRouter>
        <WalletAccounts wallet={WALLET_WITH_ACCOUNTS as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    const triggers = getDropdownTriggers();
    fireEvent.click(triggers[0]);
    await waitFor(() => screen.getByText("Rename"));
    fireEvent.click(screen.getByText("Rename"));
    expect(screen.getByDisplayValue("BTC Main")).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeInTheDocument();
  });

  it("renames an account", async () => {
    mockUpdateAccount.mockResolvedValue({} as any);
    const loadWallet = vi.fn();
    render(
      <MemoryRouter>
        <WalletAccounts wallet={WALLET_WITH_ACCOUNTS as any} loadWallet={loadWallet} setError={vi.fn()} />
      </MemoryRouter>,
    );
    const triggers = getDropdownTriggers();
    fireEvent.click(triggers[0]);
    await waitFor(() => screen.getByText("Rename"));
    fireEvent.click(screen.getByText("Rename"));
    fireEvent.change(screen.getByDisplayValue("BTC Main"), { target: { value: "BTC Renamed" } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => {
      expect(mockUpdateAccount).toHaveBeenCalledWith(1, 10, { name: "BTC Renamed" });
    });
  });

  it("opens edit address form from dropdown", async () => {
    render(
      <MemoryRouter>
        <WalletAccounts wallet={WALLET_WITH_ACCOUNTS as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    const triggers = getDropdownTriggers();
    fireEvent.click(triggers[0]);
    await waitFor(() => screen.getByText("Edit Address"));
    fireEvent.click(screen.getByText("Edit Address"));
    // Should show the address edit form
    expect(screen.getByDisplayValue("bc1q0000000000000000000000000000000000")).toBeInTheDocument();
  });

  it("shows truncated address for long addresses", () => {
    render(
      <MemoryRouter>
        <WalletAccounts wallet={WALLET_WITH_ACCOUNTS as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    // Long ETH address should be truncated
    expect(screen.getByText(/0x12345678\.\.\.345678/)).toBeInTheDocument();
  });

  it("archives an account from dropdown", async () => {
    mockUpdateAccount.mockResolvedValue({} as any);
    const loadWallet = vi.fn();
    render(
      <MemoryRouter>
        <WalletAccounts wallet={WALLET_WITH_ACCOUNTS as any} loadWallet={loadWallet} setError={vi.fn()} />
      </MemoryRouter>,
    );
    const triggers = getDropdownTriggers();
    fireEvent.click(triggers[0]);
    await waitFor(() => screen.getByText("Archive"));
    fireEvent.click(screen.getByText("Archive"));
    await waitFor(() => {
      expect(mockUpdateAccount).toHaveBeenCalledWith(1, 10, { is_archived: true });
    });
  });

  it("opens move to wallet form from dropdown", async () => {
    mockFetchWallets.mockResolvedValue({ data: [{ id: 2, name: "Other Wallet", category: "wallet" }] } as any);
    render(
      <MemoryRouter>
        <WalletAccounts wallet={WALLET_WITH_ACCOUNTS as any} loadWallet={vi.fn()} setError={vi.fn()} />
      </MemoryRouter>,
    );
    const triggers = getDropdownTriggers();
    fireEvent.click(triggers[0]);
    await waitFor(() => screen.getByText("Move to Wallet"));
    fireEvent.click(screen.getByText("Move to Wallet"));
    await waitFor(() => {
      expect(screen.getByText("Move to wallet:")).toBeInTheDocument();
    });
    expect(screen.getByText("Move")).toBeInTheDocument();
  });
});
