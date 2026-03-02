import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Mock the API module
vi.mock("../api/client", () => ({
  fetchSettings: vi.fn(),
  updateSettings: vi.fn(),
  resetDatabase: vi.fn(),
}));

import Settings from "./Settings";
import { fetchSettings, updateSettings } from "../api/client";

const mockFetchSettings = vi.mocked(fetchSettings);
const mockUpdateSettings = vi.mocked(updateSettings);

describe("Settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading spinner initially", () => {
    mockFetchSettings.mockReturnValue(new Promise(() => {}) as any);
    render(<Settings />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders settings form after loading", async () => {
    mockFetchSettings.mockResolvedValue({
      data: { default_cost_basis_method: "fifo", base_currency: "USD", long_term_threshold_days: "365" },
    } as any);
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText("Settings")).toBeInTheDocument();
    });
    expect(screen.getByText("Default Cost Basis Method")).toBeInTheDocument();
    expect(screen.getByText("Base Currency")).toBeInTheDocument();
    expect(screen.getByText("Long-Term Threshold (days)")).toBeInTheDocument();
  });

  it("shows error banner on load failure", async () => {
    mockFetchSettings.mockRejectedValue({
      response: { data: { detail: "Server error" } },
    });
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText("Server error")).toBeInTheDocument();
    });
  });

  it("saves settings on button click", async () => {
    mockFetchSettings.mockResolvedValue({
      data: { default_cost_basis_method: "fifo", base_currency: "USD" },
    } as any);
    mockUpdateSettings.mockResolvedValue({} as any);
    render(<Settings />);
    await waitFor(() => screen.getByText("Save Settings"));
    fireEvent.click(screen.getByText("Save Settings"));
    await waitFor(() => {
      expect(screen.getByText("Settings saved.")).toBeInTheDocument();
    });
    expect(mockUpdateSettings).toHaveBeenCalled();
  });

  it("renders danger zone with reset button", async () => {
    mockFetchSettings.mockResolvedValue({
      data: { default_cost_basis_method: "fifo" },
    } as any);
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText("Danger Zone")).toBeInTheDocument();
    });
    expect(screen.getByText("Reset Database")).toBeInTheDocument();
  });
});
