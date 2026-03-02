import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import EmptyState from "./EmptyState";

describe("EmptyState", () => {
  it("renders title", () => {
    render(<EmptyState title="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    render(<EmptyState title="Empty" description="Add some items" />);
    expect(screen.getByText("Add some items")).toBeInTheDocument();
  });

  it("does not render description when omitted", () => {
    const { container } = render(<EmptyState title="Empty" />);
    expect(container.querySelectorAll("p")).toHaveLength(0);
  });

  it("renders action link when label and path provided", () => {
    render(
      <MemoryRouter>
        <EmptyState title="Empty" actionLabel="Add Item" actionTo="/add" />
      </MemoryRouter>,
    );
    const link = screen.getByText("Add Item");
    expect(link).toBeInTheDocument();
    expect(link.closest("a")).toHaveAttribute("href", "/add");
  });

  it("does not render action link without actionLabel", () => {
    render(
      <MemoryRouter>
        <EmptyState title="Empty" />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
