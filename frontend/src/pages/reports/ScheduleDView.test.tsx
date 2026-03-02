import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ScheduleDView from "./ScheduleDView";

const MOCK_DATA = {
  lines: [
    { line: "1a", description: "Short-term trades from 8949", proceeds: "10000.00", cost_basis: "8000.00", gain_loss: "2000.00" },
    { line: "7", description: "Net short-term capital gain or loss", proceeds: "10000.00", cost_basis: "8000.00", gain_loss: "2000.00" },
  ],
  net_short_term: "2000.00",
  net_long_term: "0.00",
  combined_net: "2000.00",
};

describe("ScheduleDView", () => {
  it("renders table with lines", () => {
    render(<ScheduleDView data={MOCK_DATA} />);
    expect(screen.getByText("1a")).toBeInTheDocument();
    expect(screen.getByText("Short-term trades from 8949")).toBeInTheDocument();
  });

  it("renders summary totals", () => {
    render(<ScheduleDView data={MOCK_DATA} />);
    expect(screen.getByText(/Net Short-Term/)).toBeInTheDocument();
    expect(screen.getByText(/Net Long-Term/)).toBeInTheDocument();
    expect(screen.getByText(/Combined/)).toBeInTheDocument();
  });

  it("highlights summary lines", () => {
    const { container } = render(<ScheduleDView data={MOCK_DATA} />);
    const rows = container.querySelectorAll("tr");
    // Row for line "7" should have bold font weight (summary line)
    const line7Row = Array.from(rows).find((r) => r.textContent?.includes("7"));
    expect(line7Row?.style.fontWeight).toBe("600");
  });
});
