import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import StickyPagination from "./TransactionPagination";

describe("StickyPagination", () => {
  it("renders page numbers", () => {
    render(
      <StickyPagination page={1} totalPages={5} total={100} onPageChange={vi.fn()} />,
    );
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("highlights current page", () => {
    render(
      <StickyPagination page={3} totalPages={5} total={100} onPageChange={vi.fn()} />,
    );
    const activeBtn = screen.getByText("3");
    expect(activeBtn.style.backgroundColor).toContain("var(--accent)");
  });

  it("calls onPageChange when clicking a page", () => {
    const onChange = vi.fn();
    render(
      <StickyPagination page={1} totalPages={5} total={100} onPageChange={onChange} />,
    );
    fireEvent.click(screen.getByText("3"));
    expect(onChange).toHaveBeenCalledWith(3);
  });

  it("shows prev/next buttons", () => {
    render(
      <StickyPagination page={2} totalPages={5} total={100} onPageChange={vi.fn()} />,
    );
    expect(screen.getByText("‹")).toBeInTheDocument();
    expect(screen.getByText("›")).toBeInTheDocument();
  });

  it("disables prev on first page", () => {
    render(
      <StickyPagination page={1} totalPages={5} total={100} onPageChange={vi.fn()} />,
    );
    const prevBtn = screen.getByText("‹");
    expect(prevBtn).toBeDisabled();
  });

  it("shows total count", () => {
    render(
      <StickyPagination page={1} totalPages={5} total={100} onPageChange={vi.fn()} />,
    );
    expect(screen.getByText(/100/)).toBeInTheDocument();
  });

  it("shows ellipsis for many pages", () => {
    render(
      <StickyPagination page={5} totalPages={20} total={500} onPageChange={vi.fn()} />,
    );
    // The component uses "…" (unicode ellipsis) not "..."
    expect(screen.getAllByText("…").length).toBeGreaterThanOrEqual(1);
  });
});
