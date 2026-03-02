import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../api/client", () => ({
  fetchDailyValues: vi.fn(),
  fetchPortfolioHoldings: vi.fn(),
  fetchPortfolioStats: vi.fn(),
  fetchTransactionErrorCount: vi.fn(),
  refreshCurrentPrices: vi.fn(),
  backfillPrices: vi.fn(),
  hideAsset: vi.fn(),
  unhideAsset: vi.fn(),
  fetchHiddenAssets: vi.fn(),
}));

import Dashboard from "./Dashboard";
import {
  fetchDailyValues,
  fetchPortfolioHoldings,
  fetchPortfolioStats,
  fetchTransactionErrorCount,
  fetchHiddenAssets,
  refreshCurrentPrices,
  backfillPrices,
  hideAsset,
  unhideAsset,
} from "../../api/client";

const mockDailyValues = vi.mocked(fetchDailyValues);
const mockHoldings = vi.mocked(fetchPortfolioHoldings);
const mockStats = vi.mocked(fetchPortfolioStats);
const mockErrorCount = vi.mocked(fetchTransactionErrorCount);
const mockHiddenAssets = vi.mocked(fetchHiddenAssets);
const mockRefreshPrices = vi.mocked(refreshCurrentPrices);
const mockBackfill = vi.mocked(backfillPrices);
const mockHideAsset = vi.mocked(hideAsset);
const mockUnhideAsset = vi.mocked(unhideAsset);

const EMPTY_DAILY = {
  data_points: [],
  summary: { current_value: "0", total_cost_basis: "0", unrealized_gain: "0", unrealized_gain_pct: "0" },
};

const FULL_DAILY = {
  data_points: [{ date: "2024-01-01", total_value_usd: "10000" }],
  summary: { current_value: "10000", total_cost_basis: "8000", unrealized_gain: "2000", unrealized_gain_pct: "25" },
};

const FULL_HOLDINGS = {
  holdings: [
    { asset_id: 1, asset_symbol: "BTC", asset_name: "Bitcoin", quantity: "0.5", market_value_usd: "10000", cost_basis_usd: "8000", unrealized_gain_usd: "2000", allocation_pct: "100", total_quantity: "0.5", total_cost_basis_usd: "8000", current_price_usd: "20000", roi_pct: "25", wallet_breakdown: [] },
  ],
  total_portfolio_value: "10000",
};

const FULL_STATS = {
  total_in: "8000", total_out: "0", total_income: "0", total_expenses: "0", total_fees: "50", realized_gains: "0",
};

function setupFullData() {
  mockDailyValues.mockResolvedValue({ data: FULL_DAILY } as any);
  mockHoldings.mockResolvedValue({ data: FULL_HOLDINGS } as any);
  mockStats.mockResolvedValue({ data: FULL_STATS } as any);
}

describe("Dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHiddenAssets.mockResolvedValue({ data: [] } as any);
    mockErrorCount.mockResolvedValue({ data: { error_count: 0 } } as any);
  });

  it("shows loading spinner initially", () => {
    mockDailyValues.mockReturnValue(new Promise(() => {}) as any);
    mockHoldings.mockReturnValue(new Promise(() => {}) as any);
    mockStats.mockReturnValue(new Promise(() => {}) as any);
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders portfolio after data loads", async () => {
    setupFullData();
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Portfolio")).toBeInTheDocument();
    });
    expect(screen.getByText("Total Value")).toBeInTheDocument();
    expect(screen.getByText("Cost Basis")).toBeInTheDocument();
    expect(screen.getByText("Unrealized Gain")).toBeInTheDocument();
  });

  it("shows error banner on failure", async () => {
    mockDailyValues.mockRejectedValue({
      response: { data: { detail: "API failure" } },
    });
    mockHoldings.mockRejectedValue({});
    mockStats.mockRejectedValue({});
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("API failure")).toBeInTheDocument();
    });
  });

  it("shows Getting Started when no data", async () => {
    mockDailyValues.mockResolvedValue({ data: EMPTY_DAILY } as any);
    mockHoldings.mockResolvedValue({ data: { holdings: [], total_portfolio_value: "0" } } as any);
    mockStats.mockResolvedValue({ data: { total_in: "0", total_out: "0", total_income: "0", total_expenses: "0", total_fees: "0", realized_gains: "0" } } as any);
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Getting Started")).toBeInTheDocument();
    });
    expect(screen.getByText("Import Transactions")).toBeInTheDocument();
    expect(screen.getByText("Import from Koinly")).toBeInTheDocument();
  });

  it("shows tax error banner when errors exist", async () => {
    mockErrorCount.mockResolvedValue({ data: { error_count: 5 } } as any);
    setupFullData();
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("5 Transactions with Tax Errors")).toBeInTheDocument();
    });
    expect(screen.getByText("View Errors")).toBeInTheDocument();
  });

  it("renders date preset buttons", async () => {
    setupFullData();
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Portfolio"));
    expect(screen.getByText("YTD")).toBeInTheDocument();
    expect(screen.getByText("1M")).toBeInTheDocument();
    expect(screen.getByText("3M")).toBeInTheDocument();
    expect(screen.getByText("6M")).toBeInTheDocument();
    expect(screen.getByText("1Y")).toBeInTheDocument();
    expect(screen.getByText("ALL")).toBeInTheDocument();
  });

  it("changes date range on preset click", async () => {
    setupFullData();
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Portfolio"));
    fireEvent.click(screen.getByText("3M"));
    // Clicking 3M triggers a re-fetch with new date range
    await waitFor(() => {
      expect(mockDailyValues).toHaveBeenCalledTimes(2);
    });
  });

  it("renders Backfill Chart and Refresh Prices buttons", async () => {
    setupFullData();
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Portfolio"));
    expect(screen.getByText("Backfill Chart")).toBeInTheDocument();
    expect(screen.getByText("Refresh Prices")).toBeInTheDocument();
  });

  it("calls refresh prices on button click", async () => {
    setupFullData();
    mockRefreshPrices.mockResolvedValue({} as any);
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Portfolio"));
    fireEvent.click(screen.getByText("Refresh Prices"));
    await waitFor(() => {
      expect(mockRefreshPrices).toHaveBeenCalled();
    });
  });

  it("calls backfill on button click", async () => {
    setupFullData();
    mockBackfill.mockResolvedValue({} as any);
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Portfolio"));
    fireEvent.click(screen.getByText("Backfill Chart"));
    await waitFor(() => {
      expect(mockBackfill).toHaveBeenCalled();
    });
  });

  it("shows hidden assets toggle when assets are hidden", async () => {
    mockHiddenAssets.mockResolvedValue({ data: [{ id: 99, symbol: "SHIB", name: "Shiba Inu" }] } as any);
    setupFullData();
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Portfolio"));
    await waitFor(() => {
      expect(screen.getByText(/Show 1 hidden asset/)).toBeInTheDocument();
    });
  });

  it("reveals hidden assets and allows unhiding", async () => {
    mockHiddenAssets.mockResolvedValue({ data: [{ id: 99, symbol: "SHIB", name: "Shiba Inu" }] } as any);
    mockUnhideAsset.mockResolvedValue({} as any);
    mockHoldings.mockResolvedValue({ data: FULL_HOLDINGS } as any);
    setupFullData();
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Portfolio"));
    await waitFor(() => screen.getByText(/Show 1 hidden asset/));
    fireEvent.click(screen.getByText(/Show 1 hidden asset/));
    expect(screen.getByText("SHIB")).toBeInTheDocument();
    expect(screen.getByText("Shiba Inu")).toBeInTheDocument();
    expect(screen.getByText("Unhide")).toBeInTheDocument();
  });

  it("hides an asset from holdings", async () => {
    mockHideAsset.mockResolvedValue({} as any);
    setupFullData();
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Portfolio"));
    // HoldingsSummary renders with Hide buttons
    await waitFor(() => {
      expect(screen.getAllByText("Hide").length).toBeGreaterThan(0);
    });
    const hideButtons = screen.getAllByText("Hide");
    fireEvent.click(hideButtons[0]);
    await waitFor(() => {
      expect(mockHideAsset).toHaveBeenCalledWith(1);
    });
  });
});
