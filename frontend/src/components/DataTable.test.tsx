import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import DataTable from "./DataTable";

interface TestItem {
  id: number;
  name: string;
  value: number;
}

const ITEMS: TestItem[] = [
  { id: 1, name: "Banana", value: 200 },
  { id: 2, name: "Apple", value: 100 },
  { id: 3, name: "Cherry", value: 300 },
];

const COLUMNS = [
  { key: "name", header: "Name" },
  { key: "value", header: "Value" },
];

describe("DataTable", () => {
  it("renders headers and data", () => {
    render(<DataTable columns={COLUMNS} data={ITEMS} keyField="id" />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Value")).toBeInTheDocument();
    expect(screen.getByText("Banana")).toBeInTheDocument();
    expect(screen.getByText("Apple")).toBeInTheDocument();
    expect(screen.getByText("Cherry")).toBeInTheDocument();
  });

  it("sorts ascending on first click", () => {
    render(<DataTable columns={COLUMNS} data={ITEMS} keyField="id" />);
    fireEvent.click(screen.getByText("Name"));
    const cells = screen.getAllByRole("cell");
    const names = cells.filter((_, i) => i % 2 === 0).map((c) => c.textContent);
    expect(names).toEqual(["Apple", "Banana", "Cherry"]);
  });

  it("sorts descending on second click", () => {
    render(<DataTable columns={COLUMNS} data={ITEMS} keyField="id" />);
    const nameHeader = screen.getByText("Name");
    fireEvent.click(nameHeader);
    // After first click, header text is "Name ▲" so use the th element directly
    fireEvent.click(nameHeader.closest("th")!);
    const cells = screen.getAllByRole("cell");
    const names = cells.filter((_, i) => i % 2 === 0).map((c) => c.textContent);
    expect(names).toEqual(["Cherry", "Banana", "Apple"]);
  });

  it("uses custom render function", () => {
    const cols = [
      { key: "name", header: "Name", render: (row: TestItem) => <strong>{row.name}!</strong> },
    ];
    render(<DataTable columns={cols} data={ITEMS} keyField="id" />);
    expect(screen.getByText("Banana!")).toBeInTheDocument();
  });

  it("respects sortable=false", () => {
    const cols = [
      { key: "name", header: "Name", sortable: false },
      { key: "value", header: "Value" },
    ];
    render(<DataTable columns={cols} data={ITEMS} keyField="id" />);
    fireEvent.click(screen.getByText("Name"));
    // No sort indicator should appear for non-sortable column
    expect(screen.getByText("Name").textContent).toBe("Name");
  });

  it("shows sort indicator", () => {
    render(<DataTable columns={COLUMNS} data={ITEMS} keyField="id" />);
    const nameHeader = screen.getByText("Name");
    fireEvent.click(nameHeader);
    const th = nameHeader.closest("th")!;
    expect(th.textContent).toContain("▲");
    fireEvent.click(th);
    expect(th.textContent).toContain("▼");
  });
});
