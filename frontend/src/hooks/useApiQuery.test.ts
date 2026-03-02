import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useApiQuery } from "./useApiQuery";

describe("useApiQuery", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("starts in loading state", () => {
    const fetcher = vi.fn(() => new Promise<string>(() => {})); // never resolves
    const { result } = renderHook(() => useApiQuery(fetcher, []));
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe("");
  });

  it("returns data on success", async () => {
    const fetcher = vi.fn(() => Promise.resolve("hello"));
    const { result } = renderHook(() => useApiQuery(fetcher, []));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBe("hello");
    expect(result.current.error).toBe("");
  });

  it("returns error on failure", async () => {
    const fetcher = vi.fn(() => Promise.reject(new Error("boom")));
    const { result } = renderHook(() => useApiQuery(fetcher, []));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe("boom");
  });

  it("parses axios-style error detail", async () => {
    const fetcher = vi.fn(() =>
      Promise.reject({ response: { data: { detail: "Not found" } } }),
    );
    const { result } = renderHook(() => useApiQuery(fetcher, []));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe("Not found");
  });

  it("refetch re-fetches data", async () => {
    let count = 0;
    const fetcher = vi.fn(() => Promise.resolve(++count));
    const { result } = renderHook(() => useApiQuery(fetcher, []));
    await waitFor(() => expect(result.current.data).toBe(1));
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.data).toBe(2));
  });

  it("does not fetch when enabled=false", async () => {
    const fetcher = vi.fn(() => Promise.resolve("data"));
    const { result } = renderHook(() =>
      useApiQuery(fetcher, [], { enabled: false }),
    );
    expect(result.current.loading).toBe(false);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("refetches when deps change", async () => {
    let count = 0;
    const fetcher = vi.fn(() => Promise.resolve(++count));
    const { result, rerender } = renderHook(
      ({ dep }: { dep: number }) => useApiQuery(fetcher, [dep]),
      { initialProps: { dep: 1 } },
    );
    await waitFor(() => expect(result.current.data).toBe(1));
    rerender({ dep: 2 });
    await waitFor(() => expect(result.current.data).toBe(2));
  });

  it("calls onError callback", async () => {
    const onError = vi.fn();
    const fetcher = vi.fn(() => Promise.reject(new Error("fail")));
    renderHook(() => useApiQuery(fetcher, [], { onError }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith("fail"));
  });
});
