import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock recharts to avoid SVG rendering issues in jsdom
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: any) => <div data-testid="chart-container">{children}</div>,
  AreaChart: ({ children }: any) => <div data-testid="area-chart">{children}</div>,
  Area: () => <div data-testid="area" />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  CartesianGrid: () => <div />,
}));

import { vi } from "vitest";
import PortfolioChart from "./PortfolioChart";

describe("PortfolioChart", () => {
  it("shows empty message when no data", () => {
    render(<PortfolioChart chartData={[]} />);
    expect(screen.getByText(/No chart data available/)).toBeInTheDocument();
  });

  it("renders chart when data provided", () => {
    const chartData = [
      { date: "2024-01-01", value: 10000 },
      { date: "2024-02-01", value: 12000 },
      { date: "2024-03-01", value: 11000 },
    ];
    render(<PortfolioChart chartData={chartData} />);
    expect(screen.getByTestId("chart-container")).toBeInTheDocument();
    expect(screen.getByTestId("area-chart")).toBeInTheDocument();
  });
});
