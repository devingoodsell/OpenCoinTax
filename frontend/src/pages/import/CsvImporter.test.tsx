import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../api/client", () => ({
  fetchWallets: vi.fn(),
  uploadCsv: vi.fn(),
  confirmImport: vi.fn(),
}));

import CsvImport from "./CsvImporter";
import { fetchWallets, uploadCsv, confirmImport } from "../../api/client";

const mockFetchWallets = vi.mocked(fetchWallets);
const mockUploadCsv = vi.mocked(uploadCsv);
const mockConfirmImport = vi.mocked(confirmImport);

describe("CsvImport", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchWallets.mockResolvedValue({
      data: [
        { id: 1, name: "My Exchange" },
        { id: 2, name: "My Ledger" },
      ],
    } as any);
  });

  it("renders select-wallet step initially", async () => {
    render(
      <MemoryRouter>
        <CsvImport />
      </MemoryRouter>,
    );
    expect(screen.getByText("Select Wallet")).toBeInTheDocument();
    expect(screen.getByText("Next")).toBeDisabled();
  });

  it("renders step indicators", () => {
    render(
      <MemoryRouter>
        <CsvImport />
      </MemoryRouter>,
    );
    expect(screen.getByText("1. select wallet")).toBeInTheDocument();
    expect(screen.getByText("2. upload")).toBeInTheDocument();
  });

  it("populates wallet dropdown from API", async () => {
    render(
      <MemoryRouter>
        <CsvImport />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("My Exchange")).toBeInTheDocument();
    });
  });

  it("navigates to upload step when wallet selected", async () => {
    render(
      <MemoryRouter>
        <CsvImport />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("My Exchange")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "1" } });
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByText("Upload CSV")).toBeInTheDocument();
  });

  it("shows preview after upload", async () => {
    mockUploadCsv.mockResolvedValue({
      data: {
        detected_format: "generic",
        rows: [
          {
            row_number: 1,
            status: "valid",
            error_message: null,
            datetime_utc: "2024-01-01T00:00:00Z",
            type: "buy",
            from_amount: "1000",
            from_asset: "USD",
            to_amount: "0.015",
            to_asset: "BTC",
            fee_amount: null,
            fee_asset: null,
            net_value_usd: "1000",
            description: null,
            tx_hash: null,
          },
        ],
        total_rows: 1,
        valid_rows: 1,
        warning_rows: 0,
        error_rows: 0,
      },
    } as any);

    render(
      <MemoryRouter>
        <CsvImport />
      </MemoryRouter>,
    );

    await waitFor(() => screen.getByText("My Exchange"));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "1" } });
    fireEvent.click(screen.getByText("Next"));

    const fileInput = document.querySelector('input[type="file"]')!;
    fireEvent.change(fileInput, { target: { files: [new File(["data"], "data.csv")] } });
    fireEvent.click(screen.getByText(/Upload & Parse/));

    await waitFor(() => {
      expect(screen.getByText("Preview")).toBeInTheDocument();
    });
    expect(screen.getByText(/Valid:/)).toBeInTheDocument();
  });

  it("shows done step after confirm", async () => {
    mockUploadCsv.mockResolvedValue({
      data: {
        detected_format: "generic",
        rows: [{ row_number: 1, status: "valid", error_message: null, datetime_utc: "2024-01-01", type: "buy", from_amount: "100", from_asset: "USD", to_amount: "0.01", to_asset: "BTC", fee_amount: null, fee_asset: null, net_value_usd: "100", description: null, tx_hash: null }],
        total_rows: 1,
        valid_rows: 1,
        warning_rows: 0,
        error_rows: 0,
      },
    } as any);
    mockConfirmImport.mockResolvedValue({
      data: { transactions_imported: 1, transactions_skipped: 0 },
    } as any);

    render(
      <MemoryRouter>
        <CsvImport />
      </MemoryRouter>,
    );

    await waitFor(() => screen.getByText("My Exchange"));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "1" } });
    fireEvent.click(screen.getByText("Next"));

    const fileInput = document.querySelector('input[type="file"]')!;
    fireEvent.change(fileInput, { target: { files: [new File(["data"], "data.csv")] } });
    fireEvent.click(screen.getByText(/Upload & Parse/));

    await waitFor(() => screen.getByText("Preview"));
    fireEvent.click(screen.getByText(/Confirm Import/));

    await waitFor(() => {
      expect(screen.getByText("Import Complete")).toBeInTheDocument();
    });
    expect(screen.getByText("View Transactions")).toBeInTheDocument();
  });
});
