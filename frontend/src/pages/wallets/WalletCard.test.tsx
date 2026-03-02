import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../api/client", () => ({
  updateWallet: vi.fn(),
}));

import WalletCard, { CategoryBadge, WALLET_TYPES } from "./WalletCard";
import { updateWallet } from "../../api/client";
import type { WalletListItem } from "../../api/client";

const mockUpdateWallet = vi.mocked(updateWallet);

const MOCK_WALLET: WalletListItem = {
  id: 1,
  name: "My Ledger",
  type: "hardware",
  category: "wallet",
  provider: "ledger",
  notes: null,
  is_archived: false,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  account_count: 3,
  transaction_count: 50,
  total_value_usd: "5000.00",
  total_cost_basis_usd: "3000.00",
};

/** The DropdownMenu default trigger is an SVG button (no text). Find it. */
function getDropdownTrigger() {
  // The only button in WalletCard's non-edit view is the dropdown trigger
  return screen.getByRole("button");
}

describe("CategoryBadge", () => {
  it("renders exchange badge", () => {
    render(<CategoryBadge category="exchange" />);
    expect(screen.getByText("Exchange")).toBeInTheDocument();
  });

  it("renders wallet badge", () => {
    render(<CategoryBadge category="wallet" />);
    expect(screen.getByText("Wallet")).toBeInTheDocument();
  });
});

describe("WALLET_TYPES", () => {
  it("contains expected types", () => {
    expect(WALLET_TYPES).toContain("exchange");
    expect(WALLET_TYPES).toContain("hardware");
    expect(WALLET_TYPES).toContain("software");
  });
});

describe("WalletCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders wallet name and type", () => {
    render(
      <MemoryRouter>
        <WalletCard
          wallet={MOCK_WALLET}
          onReload={vi.fn()}
          onDelete={vi.fn()}
          setError={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("My Ledger")).toBeInTheDocument();
  });

  it("renders account count and transaction count", () => {
    render(
      <MemoryRouter>
        <WalletCard
          wallet={MOCK_WALLET}
          onReload={vi.fn()}
          onDelete={vi.fn()}
          setError={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/3 accounts/)).toBeInTheDocument();
    expect(screen.getByText(/50 txns/)).toBeInTheDocument();
  });

  it("renders value and cost basis", () => {
    render(
      <MemoryRouter>
        <WalletCard
          wallet={MOCK_WALLET}
          onReload={vi.fn()}
          onDelete={vi.fn()}
          setError={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("$5,000.00")).toBeInTheDocument();
  });

  it("links to wallet detail page", () => {
    render(
      <MemoryRouter>
        <WalletCard
          wallet={MOCK_WALLET}
          onReload={vi.fn()}
          onDelete={vi.fn()}
          setError={vi.fn()}
        />
      </MemoryRouter>,
    );
    const links = screen.getAllByRole("link");
    expect(links.some((l) => l.getAttribute("href") === "/wallets/1")).toBe(true);
  });

  it("shows provider and type info", () => {
    render(
      <MemoryRouter>
        <WalletCard
          wallet={MOCK_WALLET}
          onReload={vi.fn()}
          onDelete={vi.fn()}
          setError={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/hardware/)).toBeInTheDocument();
    expect(screen.getByText(/ledger/)).toBeInTheDocument();
  });

  it("shows edit form when Edit clicked from dropdown", async () => {
    render(
      <MemoryRouter>
        <WalletCard
          wallet={MOCK_WALLET}
          onReload={vi.fn()}
          onDelete={vi.fn()}
          setError={vi.fn()}
        />
      </MemoryRouter>,
    );
    // Open dropdown via SVG trigger button
    fireEvent.click(getDropdownTrigger());
    await waitFor(() => {
      expect(screen.getByText("Edit")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Edit"));
    // Should now show edit form
    expect(screen.getByDisplayValue("My Ledger")).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("saves edited wallet", async () => {
    mockUpdateWallet.mockResolvedValue({} as any);
    const onReload = vi.fn();
    render(
      <MemoryRouter>
        <WalletCard
          wallet={MOCK_WALLET}
          onReload={onReload}
          onDelete={vi.fn()}
          setError={vi.fn()}
        />
      </MemoryRouter>,
    );
    // Open dropdown and click Edit
    fireEvent.click(getDropdownTrigger());
    await waitFor(() => screen.getByText("Edit"));
    fireEvent.click(screen.getByText("Edit"));

    // Modify name and submit
    fireEvent.change(screen.getByDisplayValue("My Ledger"), { target: { value: "Updated Ledger" } });
    fireEvent.submit(screen.getByText("Save").closest("form")!);

    await waitFor(() => {
      expect(mockUpdateWallet).toHaveBeenCalledWith(1, expect.objectContaining({ name: "Updated Ledger" }));
    });
  });

  it("shows archived badge for archived wallets", () => {
    const archivedWallet = { ...MOCK_WALLET, is_archived: true };
    render(
      <MemoryRouter>
        <WalletCard
          wallet={archivedWallet}
          onReload={vi.fn()}
          onDelete={vi.fn()}
          setError={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("Archived")).toBeInTheDocument();
  });

  it("calls onDelete from dropdown", async () => {
    const onDelete = vi.fn();
    render(
      <MemoryRouter>
        <WalletCard
          wallet={MOCK_WALLET}
          onReload={vi.fn()}
          onDelete={onDelete}
          setError={vi.fn()}
        />
      </MemoryRouter>,
    );
    fireEvent.click(getDropdownTrigger());
    await waitFor(() => screen.getByText("Delete"));
    fireEvent.click(screen.getByText("Delete"));
    expect(onDelete).toHaveBeenCalledWith(1);
  });

  it("handles archive toggle from dropdown", async () => {
    mockUpdateWallet.mockResolvedValue({} as any);
    render(
      <MemoryRouter>
        <WalletCard
          wallet={MOCK_WALLET}
          onReload={vi.fn()}
          onDelete={vi.fn()}
          setError={vi.fn()}
        />
      </MemoryRouter>,
    );
    fireEvent.click(getDropdownTrigger());
    await waitFor(() => screen.getByText("Archive"));
    fireEvent.click(screen.getByText("Archive"));
    expect(mockUpdateWallet).toHaveBeenCalledWith(1, { is_archived: true });
  });
});
