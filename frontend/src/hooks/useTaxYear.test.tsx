import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { TaxYearProvider, useTaxYear } from "./useTaxYear";
import type { ReactNode } from "react";

function wrapper({ children }: { children: ReactNode }) {
  return <TaxYearProvider>{children}</TaxYearProvider>;
}

describe("useTaxYear", () => {
  it("returns default tax year 2025", () => {
    const { result } = renderHook(() => useTaxYear(), { wrapper });
    expect(result.current.taxYear).toBe(2025);
  });

  it("updates tax year via setTaxYear", () => {
    const { result } = renderHook(() => useTaxYear(), { wrapper });
    act(() => result.current.setTaxYear(2024));
    expect(result.current.taxYear).toBe(2024);
  });

  it("returns default context values outside provider", () => {
    const { result } = renderHook(() => useTaxYear());
    expect(result.current.taxYear).toBe(2025);
    // setTaxYear is a no-op outside provider
    act(() => result.current.setTaxYear(2024));
    expect(result.current.taxYear).toBe(2025);
  });
});
