import { createContext, useContext, useState, type ReactNode } from "react";

interface TaxYearCtx {
  taxYear: number;
  setTaxYear: (y: number) => void;
}

const TaxYearContext = createContext<TaxYearCtx>({
  taxYear: 2025,
  setTaxYear: () => {},
});

export function TaxYearProvider({ children }: { children: ReactNode }) {
  const [taxYear, setTaxYear] = useState(2025);
  return (
    <TaxYearContext.Provider value={{ taxYear, setTaxYear }}>
      {children}
    </TaxYearContext.Provider>
  );
}

export function useTaxYear() {
  return useContext(TaxYearContext);
}
