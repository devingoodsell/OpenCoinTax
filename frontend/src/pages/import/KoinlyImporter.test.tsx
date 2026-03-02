import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../api/client", () => ({
  uploadKoinly: vi.fn(),
  confirmKoinlyImport: vi.fn(),
}));

import KoinlyImportTab from "./KoinlyImporter";
import { uploadKoinly, confirmKoinlyImport } from "../../api/client";

const mockUpload = vi.mocked(uploadKoinly);
const mockConfirm = vi.mocked(confirmKoinlyImport);

describe("KoinlyImportTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders upload step initially", () => {
    render(
      <MemoryRouter>
        <KoinlyImportTab />
      </MemoryRouter>,
    );
    expect(screen.getByText("Upload Koinly CSV Files")).toBeInTheDocument();
    expect(screen.getByText(/Upload & Preview/)).toBeDisabled();
  });

  it("renders step indicators", () => {
    render(
      <MemoryRouter>
        <KoinlyImportTab />
      </MemoryRouter>,
    );
    expect(screen.getByText("1. upload")).toBeInTheDocument();
    expect(screen.getByText("2. preview")).toBeInTheDocument();
    expect(screen.getByText("3. done")).toBeInTheDocument();
  });

  it("shows preview step after successful upload", async () => {
    mockUpload.mockResolvedValue({
      data: {
        wallets: [
          { koinly_id: "k1", name: "Coinbase", mapped_type: "exchange", blockchain: "ethereum" },
        ],
        existing_wallets_list: [{ id: 1, name: "My Wallet", type: "hardware" }],
        total_transactions: 10,
        valid_transactions: 8,
        duplicate_transactions: 1,
        error_transactions: 1,
        warning_transactions: 0,
      },
    } as any);

    render(
      <MemoryRouter>
        <KoinlyImportTab />
      </MemoryRouter>,
    );

    // Simulate file selection via the file inputs
    const fileInputs = document.querySelectorAll('input[type="file"]');
    const walletsFile = new File(["wallets"], "wallets.csv", { type: "text/csv" });
    const txnsFile = new File(["txns"], "txns.csv", { type: "text/csv" });
    fireEvent.change(fileInputs[0], { target: { files: [walletsFile] } });
    fireEvent.change(fileInputs[1], { target: { files: [txnsFile] } });

    fireEvent.click(screen.getByText(/Upload & Preview/));

    await waitFor(() => {
      expect(screen.getByText("Import Preview")).toBeInTheDocument();
    });
    expect(screen.getByText("Coinbase")).toBeInTheDocument();
    expect(screen.getByText(/Total:/)).toBeInTheDocument();
  });

  it("shows error on upload failure", async () => {
    mockUpload.mockRejectedValue({
      response: { data: { detail: "Parse error" } },
    });

    render(
      <MemoryRouter>
        <KoinlyImportTab />
      </MemoryRouter>,
    );

    const fileInputs = document.querySelectorAll('input[type="file"]');
    const walletsFile = new File(["w"], "w.csv", { type: "text/csv" });
    const txnsFile = new File(["t"], "t.csv", { type: "text/csv" });
    fireEvent.change(fileInputs[0], { target: { files: [walletsFile] } });
    fireEvent.change(fileInputs[1], { target: { files: [txnsFile] } });

    fireEvent.click(screen.getByText(/Upload & Preview/));

    await waitFor(() => {
      expect(screen.getByText("Parse error")).toBeInTheDocument();
    });
  });

  it("shows done step after confirm", async () => {
    mockUpload.mockResolvedValue({
      data: {
        wallets: [],
        existing_wallets_list: [],
        total_transactions: 5,
        valid_transactions: 5,
        duplicate_transactions: 0,
        error_transactions: 0,
        warning_transactions: 0,
      },
    } as any);
    mockConfirm.mockResolvedValue({
      data: {
        wallets_created: 1,
        wallets_skipped: 0,
        accounts_created: 1,
        transactions_imported: 5,
        transactions_skipped: 0,
      },
    } as any);

    render(
      <MemoryRouter>
        <KoinlyImportTab />
      </MemoryRouter>,
    );

    const fileInputs = document.querySelectorAll('input[type="file"]');
    fireEvent.change(fileInputs[0], { target: { files: [new File(["w"], "w.csv")] } });
    fireEvent.change(fileInputs[1], { target: { files: [new File(["t"], "t.csv")] } });
    fireEvent.click(screen.getByText(/Upload & Preview/));

    await waitFor(() => {
      expect(screen.getByText(/Confirm Import/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/Confirm Import/));

    await waitFor(() => {
      expect(screen.getByText("Import Complete")).toBeInTheDocument();
    });
    expect(screen.getByText("View Wallets")).toBeInTheDocument();
    expect(screen.getByText("View Transactions")).toBeInTheDocument();
    expect(screen.getByText("Import Again")).toBeInTheDocument();
  });
});
