import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TabBar, EditMode, type EditFormState } from "./WhatIfAnalysis";
import type { TxDetail } from "./TransactionInfo";

describe("TabBar", () => {
  it("renders all tabs", () => {
    render(<TabBar active="details" onChange={vi.fn()} />);
    expect(screen.getByText("Details")).toBeInTheDocument();
    expect(screen.getByText("Ledger")).toBeInTheDocument();
    expect(screen.getByText("Cost analysis")).toBeInTheDocument();
  });

  it("calls onChange when tab clicked", () => {
    const onChange = vi.fn();
    render(<TabBar active="details" onChange={onChange} />);
    fireEvent.click(screen.getByText("Ledger"));
    expect(onChange).toHaveBeenCalledWith("ledger");
  });
});

describe("EditMode", () => {
  const mockTx: TxDetail = {
    id: 1,
    datetime_utc: "2024-01-01T00:00:00Z",
    type: "buy",
    from_amount: "1000",
    from_asset_symbol: "USD",
    to_amount: "0.015",
    to_asset_symbol: "BTC",
    fee_amount: null,
    fee_asset_symbol: null,
    fee_value_usd: null,
    from_value_usd: "1000",
    to_value_usd: "1000",
    net_value_usd: "1000",
    from_wallet_name: null,
    to_wallet_name: null,
    from_account_name: null,
    to_account_name: null,
    label: null,
    description: null,
    tx_hash: null,
    source: "csv",
    has_tax_error: false,
    tax_error: null,
    lot_assignments: [],
  };

  const mockForm: EditFormState = {
    type: "buy",
    from_amount: "1000",
    to_amount: "0.015",
    from_value_usd: "1000",
    to_value_usd: "1000",
    label: "",
  };

  it("renders edit form fields", () => {
    render(
      <EditMode tx={mockTx} editForm={mockForm} setEditForm={vi.fn()} onSave={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("Sent Amount")).toBeInTheDocument();
    expect(screen.getByText("Received Amount")).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("calls onSave when save clicked", () => {
    const onSave = vi.fn();
    render(
      <EditMode tx={mockTx} editForm={mockForm} setEditForm={vi.fn()} onSave={onSave} onCancel={vi.fn()} />,
    );
    fireEvent.click(screen.getByText("Save"));
    expect(onSave).toHaveBeenCalled();
  });

  it("calls onCancel when cancel clicked", () => {
    const onCancel = vi.fn();
    render(
      <EditMode tx={mockTx} editForm={mockForm} setEditForm={vi.fn()} onSave={vi.fn()} onCancel={onCancel} />,
    );
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });
});
