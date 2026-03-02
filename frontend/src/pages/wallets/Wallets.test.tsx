import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("../../api/client", () => ({
  fetchWallets: vi.fn(),
  createWallet: vi.fn(),
  deleteWallet: vi.fn(),
  updateWallet: vi.fn(),
}));

import Wallets from "./Wallets";
import { fetchWallets, createWallet, deleteWallet } from "../../api/client";

const mockFetchWallets = vi.mocked(fetchWallets);
const mockCreateWallet = vi.mocked(createWallet);
const mockDeleteWallet = vi.mocked(deleteWallet);

const MOCK_WALLET = {
  id: 1,
  name: "My Ledger",
  type: "hardware",
  category: "wallet",
  provider: "ledger",
  notes: null,
  is_archived: false,
  created_at: "2024-01-01",
  updated_at: "2024-01-01",
  account_count: 2,
  transaction_count: 15,
  total_value_usd: "5000.00",
  total_cost_basis_usd: "3000.00",
};

describe("Wallets", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading spinner initially", () => {
    mockFetchWallets.mockReturnValue(new Promise(() => {}) as any);
    render(
      <MemoryRouter>
        <Wallets />
      </MemoryRouter>,
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders empty state when no wallets", async () => {
    mockFetchWallets.mockResolvedValue({ data: [] } as any);
    render(
      <MemoryRouter>
        <Wallets />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("No wallets or exchanges")).toBeInTheDocument();
    });
  });

  it("renders wallet list", async () => {
    mockFetchWallets.mockResolvedValue({ data: [MOCK_WALLET] } as any);
    render(
      <MemoryRouter>
        <Wallets />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("My Ledger")).toBeInTheDocument();
    });
  });

  it("shows error banner on failure", async () => {
    mockFetchWallets.mockRejectedValue({
      response: { data: { detail: "Network error" } },
    });
    render(
      <MemoryRouter>
        <Wallets />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  it("toggles create form on Add Wallet/Exchange click", async () => {
    mockFetchWallets.mockResolvedValue({ data: [] } as any);
    render(
      <MemoryRouter>
        <Wallets />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Add Wallet/Exchange"));
    fireEvent.click(screen.getByText("Add Wallet/Exchange"));
    expect(screen.getByText("Create")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. Coinbase, Ledger Nano")).toBeInTheDocument();
    // Click again to close
    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByPlaceholderText("e.g. Coinbase, Ledger Nano")).not.toBeInTheDocument();
  });

  it("creates wallet via form", async () => {
    mockFetchWallets.mockResolvedValue({ data: [] } as any);
    mockCreateWallet.mockResolvedValue({ data: { id: 99 } } as any);
    render(
      <MemoryRouter>
        <Wallets />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Add Wallet/Exchange"));
    fireEvent.click(screen.getByText("Add Wallet/Exchange"));
    fireEvent.change(screen.getByPlaceholderText("e.g. Coinbase, Ledger Nano"), { target: { value: "New Wallet" } });
    fireEvent.change(screen.getByPlaceholderText("e.g. coinbase, ledger"), { target: { value: "trezor" } });
    fireEvent.submit(screen.getByText("Create").closest("form")!);
    await waitFor(() => {
      expect(mockCreateWallet).toHaveBeenCalledWith(
        expect.objectContaining({ name: "New Wallet", provider: "trezor" }),
      );
    });
  });

  it("shows delete confirmation modal", async () => {
    mockFetchWallets.mockResolvedValue({ data: [MOCK_WALLET] } as any);
    render(
      <MemoryRouter>
        <Wallets />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("My Ledger"));
    // The DropdownMenu trigger is an SVG button (no text). Find it among all buttons.
    const allButtons = screen.getAllByRole("button");
    const dropdownTrigger = allButtons.find((b) => b.textContent?.trim() === "");
    fireEvent.click(dropdownTrigger!);
    await waitFor(() => screen.getByText("Delete"));
    fireEvent.click(screen.getByText("Delete"));
    expect(screen.getByText("Delete wallet?")).toBeInTheDocument();
    expect(screen.getByText(/permanently delete/)).toBeInTheDocument();
  });

  it("confirms and deletes wallet", async () => {
    mockFetchWallets.mockResolvedValue({ data: [MOCK_WALLET] } as any);
    mockDeleteWallet.mockResolvedValue({} as any);
    render(
      <MemoryRouter>
        <Wallets />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("My Ledger"));
    const allButtons = screen.getAllByRole("button");
    const dropdownTrigger = allButtons.find((b) => b.textContent?.trim() === "");
    fireEvent.click(dropdownTrigger!);
    await waitFor(() => screen.getByText("Delete"));
    fireEvent.click(screen.getByText("Delete"));
    // Confirm in modal
    const deleteButtons = screen.getAllByText("Delete");
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);
    await waitFor(() => {
      expect(mockDeleteWallet).toHaveBeenCalledWith(1);
    });
  });

  it("cancels delete modal", async () => {
    mockFetchWallets.mockResolvedValue({ data: [MOCK_WALLET] } as any);
    render(
      <MemoryRouter>
        <Wallets />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("My Ledger"));
    const allButtons = screen.getAllByRole("button");
    const dropdownTrigger = allButtons.find((b) => b.textContent?.trim() === "");
    fireEvent.click(dropdownTrigger!);
    await waitFor(() => screen.getByText("Delete"));
    fireEvent.click(screen.getByText("Delete"));
    expect(screen.getByText("Delete wallet?")).toBeInTheDocument();
    // Cancel button in modal
    const cancelButtons = screen.getAllByText("Cancel");
    fireEvent.click(cancelButtons[cancelButtons.length - 1]);
    expect(screen.queryByText("Delete wallet?")).not.toBeInTheDocument();
  });

  it("renders search, sort, and show archived controls", async () => {
    mockFetchWallets.mockResolvedValue({ data: [MOCK_WALLET] } as any);
    render(
      <MemoryRouter>
        <Wallets />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("My Ledger"));
    expect(screen.getByPlaceholderText("Search wallets...")).toBeInTheDocument();
    expect(screen.getByText("Show archived")).toBeInTheDocument();
    expect(screen.getByText("Name A-Z")).toBeInTheDocument();
  });

  it("changes sort option", async () => {
    mockFetchWallets.mockResolvedValue({ data: [MOCK_WALLET] } as any);
    render(
      <MemoryRouter>
        <Wallets />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("My Ledger"));
    const sortSelect = screen.getByDisplayValue("Name A-Z");
    fireEvent.change(sortSelect, { target: { value: "created_at:desc" } });
    await waitFor(() => {
      expect(mockFetchWallets).toHaveBeenCalledWith(
        expect.objectContaining({ sort_by: "created_at", sort_dir: "desc" }),
      );
    });
  });
});
