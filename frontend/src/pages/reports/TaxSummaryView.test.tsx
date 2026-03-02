import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SummaryView, { AuditView } from "./TaxSummaryView";

const MOCK_SUMMARY = {
  total_proceeds: "50000.00",
  total_cost_basis: "30000.00",
  short_term_gains: "5000.00",
  short_term_losses: "-1000.00",
  long_term_gains: "15000.00",
  long_term_losses: "-2000.00",
  net_gain_loss: "17000.00",
  staking_income: "100.00",
  airdrop_income: "0.00",
  fork_income: "0.00",
  mining_income: "0.00",
  interest_income: "50.00",
  other_income: "0.00",
  total_income: "150.00",
  total_cost_expenses: "0.00",
  transfer_fees: "10.00",
  total_fees_usd: "10.00",
  eoy_balances: [],
};

describe("SummaryView", () => {
  it("renders capital gains section", () => {
    render(<SummaryView data={MOCK_SUMMARY} />);
    expect(screen.getByText("Capital Gains Summary")).toBeInTheDocument();
    expect(screen.getByText("Total Proceeds")).toBeInTheDocument();
    expect(screen.getByText("Net Gain/Loss")).toBeInTheDocument();
  });

  it("renders income section", () => {
    render(<SummaryView data={MOCK_SUMMARY} />);
    expect(screen.getByText("Income Summary")).toBeInTheDocument();
    expect(screen.getByText("Staking Rewards")).toBeInTheDocument();
  });

  it("renders expenses section", () => {
    render(<SummaryView data={MOCK_SUMMARY} />);
    expect(screen.getByText("Expenses")).toBeInTheDocument();
    expect(screen.getByText("Transfer Fees")).toBeInTheDocument();
  });

  it("renders end of year balances when present", () => {
    const dataWithBalances = {
      ...MOCK_SUMMARY,
      eoy_balances: [
        { asset_id: 1, symbol: "BTC", name: "Bitcoin", quantity: "0.5", cost_basis_usd: "15000.00", market_value_usd: "25000.00" },
      ],
    };
    render(<SummaryView data={dataWithBalances} />);
    expect(screen.getByText("End of Year Balances")).toBeInTheDocument();
    expect(screen.getByText("Bitcoin - BTC")).toBeInTheDocument();
  });
});

describe("AuditView", () => {
  it("renders action buttons", () => {
    render(
      <AuditView
        checks={null}
        allPassed={null}
        comparisons={null}
        onRunValidation={vi.fn()}
        onRunComparison={vi.fn()}
      />,
    );
    expect(screen.getByText("Run Invariant Checks")).toBeInTheDocument();
    expect(screen.getByText("Compare Methods")).toBeInTheDocument();
  });

  it("renders empty state when no data", () => {
    render(
      <AuditView
        checks={null}
        allPassed={null}
        comparisons={null}
        onRunValidation={vi.fn()}
        onRunComparison={vi.fn()}
      />,
    );
    expect(screen.getByText(/Run invariant checks or compare/)).toBeInTheDocument();
  });

  it("renders check results", () => {
    const checks = [
      { check_name: "Balance Check", status: "pass", details: "OK" },
      { check_name: "Lot Check", status: "fail", details: "Missing lots" },
    ];
    render(
      <AuditView
        checks={checks}
        allPassed={false}
        comparisons={null}
        onRunValidation={vi.fn()}
        onRunComparison={vi.fn()}
      />,
    );
    expect(screen.getByText("Issues Found")).toBeInTheDocument();
    expect(screen.getByText("Balance Check")).toBeInTheDocument();
  });

  it("renders comparisons", () => {
    const comparisons = [
      { method: "fifo", total_gains: "5000", total_losses: "1000", net_gain_loss: "4000", short_term_net: "1000", long_term_net: "3000" },
    ];
    render(
      <AuditView
        checks={null}
        allPassed={null}
        comparisons={comparisons}
        onRunValidation={vi.fn()}
        onRunComparison={vi.fn()}
      />,
    );
    expect(screen.getByText("Method Comparison")).toBeInTheDocument();
    expect(screen.getByText("fifo")).toBeInTheDocument();
  });

  it("calls onRunValidation on click", () => {
    const onRun = vi.fn();
    render(
      <AuditView
        checks={null}
        allPassed={null}
        comparisons={null}
        onRunValidation={onRun}
        onRunComparison={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Run Invariant Checks"));
    expect(onRun).toHaveBeenCalledOnce();
  });
});
