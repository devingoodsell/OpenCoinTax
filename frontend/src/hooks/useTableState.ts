import { useState, useMemo, useCallback } from "react";

interface UseTableStateOptions<T> {
  items: T[];
  defaultSortKey?: keyof T & string;
  defaultSortDir?: "asc" | "desc";
  pageSize?: number;
  filterFn?: (item: T, search: string) => boolean;
  sortFn?: (a: T, b: T, key: string, dir: "asc" | "desc") => number;
}

interface UseTableStateResult<T> {
  sortedItems: T[];
  pagedItems: T[];
  search: string;
  setSearch: (s: string) => void;
  sortKey: string;
  sortDir: "asc" | "desc";
  toggleSort: (key: string) => void;
  page: number;
  setPage: (p: number) => void;
  totalPages: number;
}

function defaultSort<T>(a: T, b: T, key: string, dir: "asc" | "desc"): number {
  const av = (a as Record<string, unknown>)[key];
  const bv = (b as Record<string, unknown>)[key];
  let cmp = 0;
  if (typeof av === "number" && typeof bv === "number") {
    cmp = av - bv;
  } else if (typeof av === "string" && typeof bv === "string") {
    cmp = av.localeCompare(bv);
  } else {
    cmp = String(av ?? "").localeCompare(String(bv ?? ""));
  }
  return dir === "asc" ? cmp : -cmp;
}

/**
 * Hook for managing table state: sorting, filtering, and pagination.
 *
 * @example
 * const { sortedItems, pagedItems, search, setSearch, toggleSort, page, setPage, totalPages }
 *   = useTableState({ items: holdings, defaultSortKey: "total_value_usd", defaultSortDir: "desc" });
 */
export function useTableState<T>(options: UseTableStateOptions<T>): UseTableStateResult<T> {
  const {
    items,
    defaultSortKey = "",
    defaultSortDir = "asc",
    pageSize = 0, // 0 = no pagination
    filterFn,
    sortFn = defaultSort,
  } = options;

  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<string>(defaultSortKey);
  const [sortDir, setSortDir] = useState<"asc" | "desc">(defaultSortDir);
  const [page, setPage] = useState(1);

  const toggleSort = useCallback(
    (key: string) => {
      if (key === sortKey) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir("asc");
      }
      setPage(1);
    },
    [sortKey],
  );

  const filtered = useMemo(() => {
    if (!search || !filterFn) return items;
    return items.filter((item) => filterFn(item, search));
  }, [items, search, filterFn]);

  const sortedItems = useMemo(() => {
    if (!sortKey) return filtered;
    return [...filtered].sort((a, b) => sortFn(a, b, sortKey, sortDir));
  }, [filtered, sortKey, sortDir, sortFn]);

  const totalPages = pageSize > 0 ? Math.ceil(sortedItems.length / pageSize) : 1;

  const pagedItems = useMemo(() => {
    if (pageSize <= 0) return sortedItems;
    const start = (page - 1) * pageSize;
    return sortedItems.slice(start, start + pageSize);
  }, [sortedItems, page, pageSize]);

  return {
    sortedItems,
    pagedItems,
    search,
    setSearch,
    sortKey,
    sortDir,
    toggleSort,
    page,
    setPage,
    totalPages,
  };
}
