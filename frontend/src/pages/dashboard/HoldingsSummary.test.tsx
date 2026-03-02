import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import HoldingsSummary from "./HoldingsSummary";

const MOCK_HOLDINGS = [
  {
    asset_id: 1,
    asset_symbol: "BTC",
    asset_name: "Bitcoin",
    total_quantity: "0.5",
    total_cost_basis_usd: "15000.00",
    current_price_usd: "65000.00",
    market_value_usd: "32500.00",
    roi_pct: "116.67",
    wallet_breakdown: [
      { wallet_id: 1, wallet_name: "Coinbase", quantity: "0.3", value_usd: "19500.00" },
      { wallet_id: 2, wallet_name: "Ledger", quantity: "0.2", value_usd: "13000.00" },
    ],
  },
  {
    asset_id: 2,
    asset_symbol: "ETH",
    asset_name: "Ethereum",
    total_quantity: "10",
    total_cost_basis_usd: "20000.00",
    current_price_usd: "3500.00",
    market_value_usd: "35000.00",
    roi_pct: "75.00",
    wallet_breakdown: [],
  },
  {
    asset_id: 3,
    asset_symbol: "DOGE",
    asset_name: "Dogecoin",
    total_quantity: "0",
    total_cost_basis_usd: "0.00",
    current_price_usd: "0.10",
    market_value_usd: "0.00",
    roi_pct: null,
    wallet_breakdown: [],
  },
];

describe("HoldingsSummary", () => {
  it("renders holdings table", () => {
    render(
      <MemoryRouter>
        <HoldingsSummary holdings={MOCK_HOLDINGS as any} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Holdings")).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.getByText("ETH")).toBeInTheDocument();
  });

  it("filters zero-balance holdings by default", () => {
    render(
      <MemoryRouter>
        <HoldingsSummary holdings={MOCK_HOLDINGS as any} />
      </MemoryRouter>,
    );
    // DOGE has 0.00 market value so should be hidden by default
    expect(screen.queryByText("DOGE")).not.toBeInTheDocument();
    expect(screen.getByText(/Show 1 zero-balance asset/)).toBeInTheDocument();
  });

  it("shows zero-balance when toggled", () => {
    render(
      <MemoryRouter>
        <HoldingsSummary holdings={MOCK_HOLDINGS as any} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText(/Show 1 zero-balance/));
    expect(screen.getByText("DOGE")).toBeInTheDocument();
  });

  it("searches by asset name", () => {
    render(
      <MemoryRouter>
        <HoldingsSummary holdings={MOCK_HOLDINGS as any} />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByPlaceholderText("Search assets..."), { target: { value: "bitcoin" } });
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.queryByText("ETH")).not.toBeInTheDocument();
  });

  it("sorts by clicking column headers", () => {
    render(
      <MemoryRouter>
        <HoldingsSummary holdings={MOCK_HOLDINGS as any} />
      </MemoryRouter>,
    );
    // Default sort is by market value desc
    const assetHeader = screen.getByText(/^Asset/);
    fireEvent.click(assetHeader);
    // Should now sort by asset
    expect(assetHeader.textContent).toContain("▼");
  });

  it("expands wallet breakdown on click", () => {
    render(
      <MemoryRouter>
        <HoldingsSummary holdings={MOCK_HOLDINGS as any} />
      </MemoryRouter>,
    );
    // BTC has wallet_breakdown, click its row
    const btcRow = screen.getByText("BTC").closest("tr")!;
    fireEvent.click(btcRow);
    expect(screen.getByText("Coinbase")).toBeInTheDocument();
    expect(screen.getByText("Ledger")).toBeInTheDocument();
  });

  it("renders hide button when onHide provided", () => {
    const onHide = vi.fn();
    render(
      <MemoryRouter>
        <HoldingsSummary holdings={MOCK_HOLDINGS as any} onHide={onHide} />
      </MemoryRouter>,
    );
    const hideButtons = screen.getAllByText("Hide");
    expect(hideButtons.length).toBeGreaterThan(0);
    fireEvent.click(hideButtons[0]);
    expect(onHide).toHaveBeenCalled();
  });

  it("shows empty state when no holdings match filter", () => {
    render(
      <MemoryRouter>
        <HoldingsSummary holdings={MOCK_HOLDINGS as any} />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByPlaceholderText("Search assets..."), { target: { value: "ZZZZZ" } });
    expect(screen.getByText("No holdings found.")).toBeInTheDocument();
  });
});
