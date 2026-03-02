import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { TaxYearProvider } from "./hooks/useTaxYear";
import Layout from "./components/Layout";
import Dashboard from "./pages/dashboard";
import Transactions from "./pages/transactions";
import TransactionDetail from "./pages/transaction-detail";
import Wallets from "./pages/wallets";
import WalletDetail from "./pages/wallet-detail";
import Import from "./pages/import";
import Reports from "./pages/reports";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <TaxYearProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/transactions/:id" element={<TransactionDetail />} />
            <Route path="/wallets" element={<Wallets />} />
            <Route path="/wallets/:id" element={<WalletDetail />} />
            <Route path="/import" element={<Import />} />
            <Route path="/import/koinly" element={<Navigate to="/import?tab=koinly" replace />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/audit" element={<Navigate to="/reports" replace />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </TaxYearProvider>
  );
}
