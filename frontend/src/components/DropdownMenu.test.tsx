import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import DropdownMenu from "./DropdownMenu";

const ITEMS = [
  { label: "Edit", onClick: vi.fn() },
  { label: "Delete", onClick: vi.fn(), variant: "danger" as const },
];

describe("DropdownMenu", () => {
  it("renders trigger button", () => {
    render(<DropdownMenu items={ITEMS} />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("does not show menu items initially", () => {
    render(<DropdownMenu items={ITEMS} />);
    expect(screen.queryByText("Edit")).not.toBeInTheDocument();
  });

  it("shows menu items on click", () => {
    render(<DropdownMenu items={ITEMS} />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Edit")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
  });

  it("calls item onClick and closes menu", () => {
    const onEdit = vi.fn();
    const items = [{ label: "Edit", onClick: onEdit }];
    render(<DropdownMenu items={items} />);
    fireEvent.click(screen.getByRole("button"));
    fireEvent.click(screen.getByText("Edit"));
    expect(onEdit).toHaveBeenCalledOnce();
    expect(screen.queryByText("Edit")).not.toBeInTheDocument();
  });

  it("closes on Escape key", () => {
    render(<DropdownMenu items={ITEMS} />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Edit")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("Edit")).not.toBeInTheDocument();
  });

  it("closes on outside click", async () => {
    render(
      <div>
        <div data-testid="outside">outside</div>
        <DropdownMenu items={ITEMS} />
      </div>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Edit")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByTestId("outside"));
    await waitFor(() => {
      expect(screen.queryByText("Edit")).not.toBeInTheDocument();
    });
  });

  it("renders custom trigger", () => {
    render(<DropdownMenu items={ITEMS} trigger={<span>Menu</span>} />);
    expect(screen.getByText("Menu")).toBeInTheDocument();
  });
});
