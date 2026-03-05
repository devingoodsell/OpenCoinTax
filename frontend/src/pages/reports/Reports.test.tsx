import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

vi.mock("../../api/client", () => ({
  fetchForm8949: vi.fn(),
  downloadForm8949Csv: vi.fn(),
  fetchScheduleD: vi.fn(),
  fetchReportTaxSummary: vi.fn(),
  fetchTaxYears: vi.fn().mockResolvedValue({ data: { years: [2024, 2025, 2026] } }),
  recalculate: vi.fn(),
  validateTax: vi.fn(),
  compareMethods: vi.fn(),
}));

vi.mock("../../hooks/useTaxYear", () => ({
  useTaxYear: () => ({ taxYear: 2025, setTaxYear: vi.fn() }),
  TaxYearProvider: ({ children }: { children: ReactNode }) => children,
}));

import Reports from "./Reports";
import { recalculate, fetchForm8949, fetchScheduleD, fetchReportTaxSummary, validateTax, downloadForm8949Csv, compareMethods } from "../../api/client";

const mockRecalculate = vi.mocked(recalculate);
const mockFetchForm8949 = vi.mocked(fetchForm8949);
const mockFetchScheduleD = vi.mocked(fetchScheduleD);
const mockFetchTaxSummary = vi.mocked(fetchReportTaxSummary);
const mockValidateTax = vi.mocked(validateTax);
const mockDownloadCsv = vi.mocked(downloadForm8949Csv);
const mockCompareMethods = vi.mocked(compareMethods);

const MOCK_F8949 = {
  short_term_rows: [],
  long_term_rows: [],
  short_term_totals: null,
  long_term_totals: null,
};

describe("Reports", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially while generating", () => {
    mockRecalculate.mockReturnValue(new Promise(() => {}) as any);
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>,
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders report tabs after data loads", async () => {
    mockRecalculate.mockResolvedValue({} as any);
    mockFetchForm8949.mockResolvedValue({ data: MOCK_F8949 } as any);
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Form 8949")).toBeInTheDocument();
    });
    expect(screen.getByText("Schedule D")).toBeInTheDocument();
    expect(screen.getByText("Tax Summary")).toBeInTheDocument();
    expect(screen.getByText("Audit")).toBeInTheDocument();
  });

  it("shows error on recalculate failure", async () => {
    mockRecalculate.mockRejectedValue({
      response: { data: { detail: "Calculation error" } },
    });
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Calculation error")).toBeInTheDocument();
    });
  });

  it("switches to Schedule D tab", async () => {
    mockRecalculate.mockResolvedValue({} as any);
    mockFetchForm8949.mockResolvedValue({ data: MOCK_F8949 } as any);
    mockFetchScheduleD.mockResolvedValue({
      data: {
        lines: [],
        net_short_term: "0",
        net_long_term: "0",
        combined_net: "0",
      },
    } as any);
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Form 8949"));
    fireEvent.click(screen.getByText("Schedule D"));
    await waitFor(() => {
      expect(mockFetchScheduleD).toHaveBeenCalled();
    });
  });

  it("switches to Tax Summary tab", async () => {
    mockRecalculate.mockResolvedValue({} as any);
    mockFetchForm8949.mockResolvedValue({ data: MOCK_F8949 } as any);
    mockFetchTaxSummary.mockResolvedValue({
      data: {
        total_proceeds: "0",
        total_cost_basis: "0",
        short_term_gains: "0",
        short_term_losses: "0",
        long_term_gains: "0",
        long_term_losses: "0",
        net_gain_loss: "0",
        staking_income: "0",
        airdrop_income: "0",
        fork_income: "0",
        mining_income: "0",
        interest_income: "0",
        other_income: "0",
        total_income: "0",
        total_cost_expenses: "0",
        transfer_fees: "0",
        total_fees_usd: "0",
        eoy_balances: [],
      },
    } as any);
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Form 8949"));
    fireEvent.click(screen.getByText("Tax Summary"));
    await waitFor(() => {
      expect(mockFetchTaxSummary).toHaveBeenCalled();
    });
  });

  it("switches to Audit tab with validation buttons", async () => {
    mockRecalculate.mockResolvedValue({} as any);
    mockFetchForm8949.mockResolvedValue({ data: MOCK_F8949 } as any);
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>,
    );
    // Wait for Form8949View content to appear (proves generating is done and data loaded)
    await waitFor(() => {
      expect(screen.getByText(/Short-Term/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Audit"));
    await waitFor(() => {
      expect(screen.getByText("Run Invariant Checks")).toBeInTheDocument();
    });
  });

  it("shows download and print buttons", async () => {
    mockRecalculate.mockResolvedValue({} as any);
    mockFetchForm8949.mockResolvedValue({ data: MOCK_F8949 } as any);
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText("Form 8949"));
    expect(screen.getByText("Download CSV")).toBeInTheDocument();
    expect(screen.getByText("Print PDF")).toBeInTheDocument();
  });

  it("calls download CSV on button click", async () => {
    mockRecalculate.mockResolvedValue({} as any);
    mockFetchForm8949.mockResolvedValue({ data: MOCK_F8949 } as any);
    mockDownloadCsv.mockResolvedValue({ data: new Blob(["csv data"]) } as any);
    // Mock URL.createObjectURL and URL.revokeObjectURL
    const createObjUrl = vi.fn(() => "blob:test");
    const revokeObjUrl = vi.fn();
    global.URL.createObjectURL = createObjUrl;
    global.URL.revokeObjectURL = revokeObjUrl;
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText(/Short-Term/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Download CSV"));
    await waitFor(() => {
      expect(mockDownloadCsv).toHaveBeenCalledWith(2025);
    });
  });

  it("calls print with all reports data", async () => {
    mockRecalculate.mockResolvedValue({} as any);
    mockFetchForm8949.mockResolvedValue({ data: MOCK_F8949 } as any);
    mockFetchScheduleD.mockResolvedValue({ data: { lines: [], net_short_term: "0", net_long_term: "0", combined_net: "0" } } as any);
    mockFetchTaxSummary.mockResolvedValue({ data: { total_proceeds: "0" } } as any);
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText(/Short-Term/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Print PDF"));
    await waitFor(() => {
      // Print triggers fetches for all 3 report types
      expect(mockFetchForm8949).toHaveBeenCalledTimes(2); // once on load, once for print
      expect(mockFetchScheduleD).toHaveBeenCalledWith(2025);
      expect(mockFetchTaxSummary).toHaveBeenCalledWith(2025);
    });
  });

  it("runs validation from Audit tab", async () => {
    mockRecalculate.mockResolvedValue({} as any);
    mockFetchForm8949.mockResolvedValue({ data: MOCK_F8949 } as any);
    mockValidateTax.mockResolvedValue({
      data: { results: [{ check_name: "Balance Check", status: "pass", details: "All OK" }], all_passed: true },
    } as any);
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText(/Short-Term/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Audit"));
    await waitFor(() => screen.getByText("Run Invariant Checks"));
    fireEvent.click(screen.getByText("Run Invariant Checks"));
    await waitFor(() => {
      expect(mockValidateTax).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByText("Balance Check")).toBeInTheDocument();
    });
    expect(screen.getByText("All Passed")).toBeInTheDocument();
  });

  it("runs method comparison from Audit tab", async () => {
    mockRecalculate.mockResolvedValue({} as any);
    mockFetchForm8949.mockResolvedValue({ data: MOCK_F8949 } as any);
    mockCompareMethods.mockResolvedValue({
      data: {
        comparisons: [
          { method: "FIFO", total_gains: "100", total_losses: "50", net_gain_loss: "50", short_term_net: "30", long_term_net: "20" },
        ],
      },
    } as any);
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText(/Short-Term/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Audit"));
    await waitFor(() => screen.getByText("Compare Methods"));
    fireEvent.click(screen.getByText("Compare Methods"));
    await waitFor(() => {
      expect(mockCompareMethods).toHaveBeenCalledWith(2025);
    });
    await waitFor(() => {
      expect(screen.getByText("FIFO")).toBeInTheDocument();
    });
  });
});
