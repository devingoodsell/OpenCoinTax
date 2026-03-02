import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Form8949View from "./Form8949View";

const MOCK_DATA = {
  short_term_rows: [
    {
      description: "0.5 BTC",
      date_acquired: "2024-01-01",
      date_sold: "2024-06-01",
      proceeds: "25000.00",
      cost_basis: "20000.00",
      gain_loss: "5000.00",
      checkbox_category: "A",
    },
  ],
  long_term_rows: [],
  short_term_totals: {
    proceeds: "25000.00",
    cost_basis: "20000.00",
    gain_loss: "5000.00",
  },
  long_term_totals: null,
};

describe("Form8949View", () => {
  it("renders short term section with data", () => {
    render(<Form8949View data={MOCK_DATA} />);
    expect(screen.getByText(/Part I.*Short-Term/)).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    // $25,000.00 appears in proceeds column
    expect(screen.getAllByText("$25,000.00").length).toBeGreaterThanOrEqual(1);
  });

  it("renders long term section with no rows message", () => {
    render(<Form8949View data={MOCK_DATA} />);
    expect(screen.getByText(/Part II.*Long-Term/)).toBeInTheDocument();
    expect(screen.getByText("No rows")).toBeInTheDocument();
  });

  it("renders totals row", () => {
    render(<Form8949View data={MOCK_DATA} />);
    expect(screen.getByText("Totals")).toBeInTheDocument();
    // $5,000.00 appears in both the row and totals
    expect(screen.getAllByText("$5,000.00").length).toBeGreaterThanOrEqual(2);
  });
});
