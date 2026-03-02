import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../api/client", () => ({
  fetchImportLogs: vi.fn(),
  deleteImport: vi.fn(),
  uploadCsv: vi.fn(),
  confirmImport: vi.fn(),
  fetchWallets: vi.fn(),
  uploadKoinly: vi.fn(),
  confirmKoinlyImport: vi.fn(),
}));

import Import from "./Import";
import { fetchImportLogs, fetchWallets } from "../../api/client";

const mockFetchImportLogs = vi.mocked(fetchImportLogs);
const mockFetchWallets = vi.mocked(fetchWallets);

describe("Import", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchWallets.mockResolvedValue({ data: [] } as any);
  });

  it("renders import tabs", async () => {
    mockFetchImportLogs.mockResolvedValue({ data: { items: [] } } as any);
    render(
      <MemoryRouter>
        <Import />
      </MemoryRouter>,
    );
    expect(screen.getByText("Import")).toBeInTheDocument();
    expect(screen.getByText("Ledger CSV Export")).toBeInTheDocument();
    expect(screen.getByText("Coinbase")).toBeInTheDocument();
    expect(screen.getByText("Koinly")).toBeInTheDocument();
  });

  it("shows import history when logs exist", async () => {
    mockFetchImportLogs.mockResolvedValue({
      data: {
        items: [
          {
            id: 1,
            import_type: "csv_upload",
            status: "completed",
            transactions_imported: 10,
            transactions_skipped: 2,
            started_at: "2024-01-01T00:00:00Z",
          },
        ],
      },
    } as any);
    render(
      <MemoryRouter>
        <Import />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Import History")).toBeInTheDocument();
    });
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });
});
