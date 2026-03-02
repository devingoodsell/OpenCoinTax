import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTableState } from "./useTableState";

interface Item {
  name: string;
  value: number;
}

const ITEMS: Item[] = [
  { name: "Banana", value: 2 },
  { name: "Apple", value: 1 },
  { name: "Cherry", value: 3 },
];

describe("useTableState", () => {
  it("returns items unsorted when no default sort key", () => {
    const { result } = renderHook(() =>
      useTableState({ items: ITEMS }),
    );
    expect(result.current.sortedItems).toEqual(ITEMS);
  });

  it("sorts ascending by default sort key", () => {
    const { result } = renderHook(() =>
      useTableState({ items: ITEMS, defaultSortKey: "name" }),
    );
    expect(result.current.sortedItems.map((i) => i.name)).toEqual([
      "Apple",
      "Banana",
      "Cherry",
    ]);
  });

  it("sorts descending when configured", () => {
    const { result } = renderHook(() =>
      useTableState({ items: ITEMS, defaultSortKey: "value", defaultSortDir: "desc" }),
    );
    expect(result.current.sortedItems.map((i) => i.value)).toEqual([3, 2, 1]);
  });

  it("toggleSort switches direction on same key", () => {
    const { result } = renderHook(() =>
      useTableState({ items: ITEMS, defaultSortKey: "value" }),
    );
    expect(result.current.sortDir).toBe("asc");
    act(() => result.current.toggleSort("value"));
    expect(result.current.sortDir).toBe("desc");
  });

  it("toggleSort switches to new key ascending", () => {
    const { result } = renderHook(() =>
      useTableState({ items: ITEMS, defaultSortKey: "value" }),
    );
    act(() => result.current.toggleSort("name"));
    expect(result.current.sortKey).toBe("name");
    expect(result.current.sortDir).toBe("asc");
  });

  it("filters with custom filterFn", () => {
    const { result } = renderHook(() =>
      useTableState({
        items: ITEMS,
        filterFn: (item, search) => item.name.toLowerCase().includes(search.toLowerCase()),
      }),
    );
    act(() => result.current.setSearch("app"));
    expect(result.current.sortedItems).toHaveLength(1);
    expect(result.current.sortedItems[0].name).toBe("Apple");
  });

  it("paginates correctly", () => {
    const { result } = renderHook(() =>
      useTableState({ items: ITEMS, pageSize: 2 }),
    );
    expect(result.current.pagedItems).toHaveLength(2);
    expect(result.current.totalPages).toBe(2);
    act(() => result.current.setPage(2));
    expect(result.current.pagedItems).toHaveLength(1);
  });

  it("returns all items when pageSize is 0", () => {
    const { result } = renderHook(() =>
      useTableState({ items: ITEMS, pageSize: 0 }),
    );
    expect(result.current.pagedItems).toHaveLength(3);
    expect(result.current.totalPages).toBe(1);
  });

  it("resets page on toggleSort", () => {
    const { result } = renderHook(() =>
      useTableState({ items: ITEMS, defaultSortKey: "value", pageSize: 2 }),
    );
    act(() => result.current.setPage(2));
    expect(result.current.page).toBe(2);
    act(() => result.current.toggleSort("name"));
    expect(result.current.page).toBe(1);
  });

  it("sorts numbers correctly", () => {
    const { result } = renderHook(() =>
      useTableState({ items: ITEMS, defaultSortKey: "value" }),
    );
    expect(result.current.sortedItems.map((i) => i.value)).toEqual([1, 2, 3]);
  });
});
