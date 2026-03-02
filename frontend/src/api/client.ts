import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

export default api;

// ---------- Types ----------
export interface Wallet {
  id: number;
  name: string;
  type: string;
  category: string;
  provider: string | null;
  notes: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface WalletListItem extends Wallet {
  account_count: number;
  transaction_count: number;
  total_value_usd: string | null;
  total_cost_basis_usd: string | null;
}

export interface Account {
  id: number;
  wallet_id: number;
  name: string;
  address: string;
  blockchain: string;
  last_synced_at: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface TransactionSummary {
  total: number;
  deposits: number;
  withdrawals: number;
  trades: number;
  transfers: number;
  buys: number;
  sells: number;
  other: number;
}

export interface WalletDetail extends Wallet {
  balances: {
    asset_id: number;
    symbol: string;
    quantity: string;
    cost_basis_usd: string;
    current_price_usd: string | null;
    market_value_usd: string | null;
    roi_pct: string | null;
  }[];
  accounts: Account[];
  transaction_summary: TransactionSummary;
  has_exchange_connection: boolean;
  exchange_last_synced_at: string | null;
}

export interface ExchangeConnection {
  id: number;
  wallet_id: number;
  exchange_type: string;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SyncResult {
  imported: number;
  skipped: number;
  errors: number;
  error_messages: string[];
}

// ---------- Wallets ----------
export const fetchWallets = (params?: Record<string, unknown>) =>
  api.get<WalletListItem[]>("/wallets", { params });
export const fetchWallet = (id: number) =>
  api.get<WalletDetail>(`/wallets/${id}`);
export const createWallet = (data: {
  name: string;
  type: string;
  provider?: string;
  notes?: string;
}) => api.post<Wallet>("/wallets", data);
export const updateWallet = (id: number, data: Record<string, unknown>) =>
  api.put<Wallet>(`/wallets/${id}`, data);
export const deleteWallet = (id: number) => api.delete(`/wallets/${id}`);

// ---------- Accounts ----------
export const fetchAccounts = (walletId: number, params?: Record<string, unknown>) =>
  api.get<Account[]>(`/wallets/${walletId}/accounts`, { params });
export const createAccount = (
  walletId: number,
  data: { name: string; address: string; blockchain: string }
) => api.post<Account>(`/wallets/${walletId}/accounts`, data);
export const updateAccount = (
  walletId: number,
  accountId: number,
  data: { name?: string; address?: string; blockchain?: string; is_archived?: boolean }
) => api.put<Account>(`/wallets/${walletId}/accounts/${accountId}`, data);
export const deleteAccount = (walletId: number, accountId: number) =>
  api.delete(`/wallets/${walletId}/accounts/${accountId}`);
export const syncAccount = (walletId: number, accountId: number) =>
  api.post<SyncResult>(`/wallets/${walletId}/accounts/${accountId}/sync`);
export const fetchAccountSyncStatus = (walletId: number, accountId: number) =>
  api.get(`/wallets/${walletId}/accounts/${accountId}/sync-status`);

// ---------- Exchange Connection ----------
export const createExchangeConnection = (
  walletId: number,
  data: { exchange_type: string; api_key: string; api_secret: string }
) => api.post<ExchangeConnection>(`/wallets/${walletId}/exchange-connection`, data);
export const deleteExchangeConnection = (walletId: number) =>
  api.delete(`/wallets/${walletId}/exchange-connection`);
export const syncExchange = (walletId: number) =>
  api.post<SyncResult>(`/wallets/${walletId}/exchange-sync`);

// ---------- Transactions ----------
export const fetchTransactions = (params?: Record<string, unknown>) =>
  api.get("/transactions", { params });
export const fetchTransaction = (id: number) =>
  api.get(`/transactions/${id}`);
export const createTransaction = (data: Record<string, unknown>) =>
  api.post("/transactions", data);
export const updateTransaction = (id: number, data: Record<string, unknown>) =>
  api.put(`/transactions/${id}`, data);
export const deleteTransaction = (id: number) =>
  api.delete(`/transactions/${id}`);
export const fetchTransactionErrorCount = () =>
  api.get<{ error_count: number }>("/transactions/error-count");

// ---------- Import ----------
export const uploadCsv = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/import/csv", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};
export const confirmImport = (data: {
  wallet_id: number;
  rows: number[];
}) => api.post("/import/csv/confirm", data);
export const fetchImportLogs = (params?: Record<string, unknown>) =>
  api.get("/import/logs", { params });
export const deleteImport = (logId: number) =>
  api.delete(`/import/logs/${logId}`);

// Koinly full-import
export interface WalletOption {
  id: number;
  name: string;
  type: string;
  category: string;
}

export interface KoinlyPreviewResponse {
  total_wallets: number;
  new_wallets: number;
  existing_wallets: number;
  total_transactions: number;
  valid_transactions: number;
  duplicate_transactions: number;
  error_transactions: number;
  warning_transactions: number;
  wallets: {
    koinly_id: string;
    name: string;
    koinly_type: string;
    mapped_type: string;
    blockchain: string | null;
    is_duplicate: boolean;
  }[];
  existing_wallets_list: WalletOption[];
  errors: string[];
}

export interface KoinlyConfirmResponse {
  wallets_created: number;
  wallets_skipped: number;
  accounts_created: number;
  transactions_imported: number;
  transactions_skipped: number;
  errors: string[];
}

export const uploadKoinly = (walletsFile: File, transactionsFile: File) => {
  const form = new FormData();
  form.append("wallets_file", walletsFile);
  form.append("transactions_file", transactionsFile);
  return api.post<KoinlyPreviewResponse>("/import/koinly", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};
export const confirmKoinlyImport = (walletMapping: Record<string, number | string>) =>
  api.post<KoinlyConfirmResponse>("/import/koinly/confirm", {
    wallet_mapping: walletMapping,
  });

// ---------- Tax ----------
export const recalculate = (_year?: number) =>
  api.post("/tax/recalculate");
export const fetchTaxSummary = (year: number) =>
  api.get(`/tax/summary/${year}`);
export const fetchGains = (year: number) => api.get(`/tax/gains/${year}`);
export const fetchLots = (params?: Record<string, unknown>) =>
  api.get("/tax/lots", { params });
export const validateTax = () => api.post("/tax/validate");
export const compareMethods = (year: number) =>
  api.get(`/tax/compare-methods/${year}`);

// ---------- Reports ----------
export const fetchForm8949 = (year: number) =>
  api.get(`/reports/8949/${year}`);
export const downloadForm8949Csv = (year: number) =>
  api.get(`/reports/8949/${year}/csv`, { responseType: "blob" });
export const fetchScheduleD = (year: number) =>
  api.get(`/reports/schedule-d/${year}`);
export const fetchReportTaxSummary = (year: number) =>
  api.get(`/reports/tax-summary/${year}`);

// ---------- Audit ----------
export const fetchAuditReconciliation = () => api.get("/audit/reconciliation");
export const fetchAuditMissingBasis = () => api.get("/audit/missing-basis");
export const fetchAuditSummary = () => api.get("/audit/summary");

// ---------- What-If ----------
export const fetchWhatIf = (txId: number) => api.get(`/tax/whatif/${txId}`);
export const applySpecificId = (txId: number, selections: Array<{ lot_id: number; amount: string }>) =>
  api.post(`/tax/specific-id/${txId}`, selections);

// ---------- Settings ----------
export const fetchSettings = () => api.get("/settings");
export const updateSettings = (data: Record<string, string>) =>
  api.put("/settings", data);

// ---------- Prices ----------
export const refreshCurrentPrices = () =>
  api.post<{ updated: number; failed: number; skipped: number }>("/prices/refresh-current");
export const backfillPrices = () =>
  api.post<{ total_stored: number; assets_processed: number; assets_failed: number; assets_mapped: number }>(
    "/prices/backfill", {}, { timeout: 300000 }
  );

// ---------- Portfolio ----------
export interface DailyDataPoint {
  date: string;
  total_value_usd: string;
  cost_basis_usd: string;
}

export interface DailyValuesSummary {
  current_value: string;
  total_cost_basis: string;
  unrealized_gain: string;
  unrealized_gain_pct: string;
}

export interface DailyValuesResponse {
  data_points: DailyDataPoint[];
  summary: DailyValuesSummary;
}

export interface WalletBreakdownItem {
  wallet_id: number;
  wallet_name: string;
  quantity: string;
  value_usd: string | null;
}

export interface HoldingItem {
  asset_id: number;
  asset_symbol: string;
  asset_name: string | null;
  total_quantity: string;
  total_cost_basis_usd: string;
  current_price_usd: string | null;
  market_value_usd: string | null;
  roi_pct: string | null;
  allocation_pct: string | null;
  wallet_breakdown: WalletBreakdownItem[];
}

export interface HoldingsResponse {
  holdings: HoldingItem[];
  total_portfolio_value: string;
}

export interface PortfolioStatsResponse {
  total_in: string;
  total_out: string;
  total_income: string;
  total_expenses: string;
  total_fees: string;
  realized_gains: string;
}

export const fetchDailyValues = (startDate: string, endDate: string) =>
  api.get<DailyValuesResponse>("/portfolio/daily-values", {
    params: { start_date: startDate, end_date: endDate },
  });
export const fetchPortfolioHoldings = () =>
  api.get<HoldingsResponse>("/portfolio/holdings");
export const fetchPortfolioStats = (startDate: string, endDate: string) =>
  api.get<PortfolioStatsResponse>("/portfolio/stats", {
    params: { start_date: startDate, end_date: endDate },
  });

// ---------- Assets ----------
export const hideAsset = (assetId: number) =>
  api.patch(`/assets/${assetId}/hide`);
export const unhideAsset = (assetId: number) =>
  api.patch(`/assets/${assetId}/unhide`);
export const fetchHiddenAssets = () =>
  api.get<{ id: number; symbol: string; name: string | null }[]>("/assets/hidden");

// ---------- Admin ----------
export const resetDatabase = () => api.post("/admin/reset-database");
