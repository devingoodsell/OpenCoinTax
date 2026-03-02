import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchTransactions, fetchTransactionErrorCount, fetchWallets, type WalletListItem } from "../../api/client";
import LoadingSpinner from "../../components/LoadingSpinner";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import { getTypeConfig } from "../../utils/transactionHelpers";
import TransactionCard, { type Transaction } from "./TransactionRow";
import StickyPagination from "./TransactionPagination";

function groupByDate(txns: Transaction[]): [string, Transaction[]][] {
  const groups: Map<string, Transaction[]> = new Map();
  for (const tx of txns) {
    const dateKey = new Date(tx.datetime_utc).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
    const list = groups.get(dateKey);
    if (list) list.push(tx);
    else groups.set(dateKey, [tx]);
  }
  return Array.from(groups.entries());
}

const PAGE_SIZE = 25;

export default function Transactions() {
  const [searchParams, setSearchParams] = useSearchParams();

  const accountIdParam = searchParams.get("account_id");
  const walletIdParam = searchParams.get("wallet_id");
  const page = Number(searchParams.get("page")) || 1;
  const search = searchParams.get("q") || "";
  const dateFrom = searchParams.get("from") || "";
  const dateTo = searchParams.get("to") || "";
  const assetSymbol = searchParams.get("asset") || "";
  const walletFilter = searchParams.get("wallet") || "";
  const showErrors = searchParams.get("has_errors") === "true";
  const excludedTypes = new Set(
    searchParams.get("exclude") ? searchParams.get("exclude")!.split(",") : []
  );

  const [txns, setTxns] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [wallets, setWallets] = useState<WalletListItem[]>([]);
  const [errorCount, setErrorCount] = useState(0);

  const [searchDraft, setSearchDraft] = useState(search);
  const [assetDraft, setAssetDraft] = useState(assetSymbol);

  useEffect(() => { setSearchDraft(search); }, [search]);
  useEffect(() => { setAssetDraft(assetSymbol); }, [assetSymbol]);

  function updateParams(updates: Record<string, string | null>) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      for (const [k, v] of Object.entries(updates)) {
        if (v === null || v === "" || v === "0") next.delete(k);
        else next.set(k, v);
      }
      return next;
    }, { replace: true });
  }

  function setPage(p: number) {
    updateParams({ page: p > 1 ? String(p) : null });
  }

  function setExcludedTypes(updater: (prev: Set<string>) => Set<string>) {
    const next = updater(excludedTypes);
    updateParams({
      exclude: next.size > 0 ? Array.from(next).join(",") : null,
      page: null,
    });
  }

  function clearFilters() {
    setSearchParams({});
  }

  function load() {
    setLoading(true);
    setError("");
    const params: Record<string, unknown> = { page, page_size: PAGE_SIZE };
    if (excludedTypes.size > 0) params.exclude_types = Array.from(excludedTypes).join(",");
    if (search) params.search = search;
    if (accountIdParam) params.account_id = Number(accountIdParam);
    if (walletIdParam) params.wallet_id = Number(walletIdParam);
    else if (walletFilter) params.wallet_id = Number(walletFilter);
    if (assetSymbol) params.asset_symbol = assetSymbol;
    if (showErrors) params.has_errors = true;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    fetchTransactions(params)
      .then((r) => {
        setTxns(r.data.items || []);
        setTotal(r.data.total || 0);
      })
      .catch((e) => setError(e.response?.data?.detail || "Failed to load"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    fetchTransactionErrorCount()
      .then((r) => setErrorCount(r.data.error_count))
      .catch(() => {});
    fetchWallets()
      .then((r) => setWallets(r.data))
      .catch(() => {});
  }, []);

  const excludedTypesKey = Array.from(excludedTypes).sort().join(",");
  useEffect(() => { load(); }, [page, excludedTypesKey, accountIdParam, walletIdParam, walletFilter, showErrors, dateFrom, dateTo, search, assetSymbol]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const dateGroups = groupByDate(txns);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Transactions{!loading && total > 0 && (
            <span className="text-lg font-normal ml-2" style={{ color: "var(--text-muted)" }}>
              ({total.toLocaleString()})
            </span>
          )}
        </h1>
        <Link
          to="/import"
          className="px-3 py-1.5 rounded text-sm transition-colors cursor-pointer"
          style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
        >
          Import
        </Link>
      </div>

      {/* Active filter banner */}
      {(accountIdParam || walletIdParam) && (
        <div
          className="flex items-center gap-2 mb-3 px-3 py-2 rounded text-sm"
          style={{ backgroundColor: "var(--bg-surface)", border: "1px solid var(--border-default)", color: "var(--text-secondary)" }}
        >
          <span>
            Filtered by {accountIdParam ? `account #${accountIdParam}` : `wallet #${walletIdParam}`}
          </span>
          <button
            onClick={clearFilters}
            className="text-xs px-2 py-0.5 rounded hover:underline"
            style={{ color: "var(--accent)" }}
          >
            Clear filter
          </button>
        </div>
      )}

      {/* Type toggle pills */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {(["buy", "sell", "trade", "transfer", "deposit", "withdrawal",
          "staking_reward", "airdrop", "mining", "interest"] as const).map((t) => {
          const cfg = getTypeConfig(t);
          const isActive = !excludedTypes.has(t);
          return (
            <button
              key={t}
              onClick={() => {
                setExcludedTypes((prev) => {
                  const next = new Set(prev);
                  if (next.has(t)) next.delete(t);
                  else next.add(t);
                  return next;
                });
              }}
              className="flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-all"
              style={{
                backgroundColor: isActive ? cfg.bg : "transparent",
                color: isActive ? cfg.color : "var(--text-muted)",
                border: `1px solid ${isActive ? cfg.color + "40" : "var(--border-default)"}`,
                opacity: isActive ? 1 : 0.5,
              }}
            >
              <span>{cfg.icon}</span>
              {cfg.label}
            </button>
          );
        })}
        {excludedTypes.size > 0 && (
          <button
            onClick={() => setExcludedTypes(() => new Set())}
            className="px-2.5 py-1 rounded-full text-xs transition-colors"
            style={{ color: "var(--accent)" }}
          >
            Show all
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={walletIdParam ?? walletFilter}
          onChange={(e) => {
            const updates: Record<string, string | null> = { wallet: e.target.value || null, page: null };
            if (walletIdParam) updates.wallet_id = null;
            updateParams(updates);
          }}
          className="rounded px-2 py-1 text-sm"
        >
          <option value="">All wallets</option>
          {wallets.map((w) => (
            <option key={w.id} value={w.id}>{w.name}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Token (e.g. ETH, BTC)..."
          value={assetDraft}
          onChange={(e) => setAssetDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") updateParams({ asset: assetDraft || null, page: null }); }}
          onBlur={() => { if (assetDraft !== assetSymbol) updateParams({ asset: assetDraft || null, page: null }); }}
          className="rounded px-2 py-1 text-sm w-40"
          style={{
            backgroundColor: "var(--bg-surface)",
            color: "var(--text-primary)",
            border: "1px solid var(--border-default)",
          }}
        />
        <input
          type="text"
          placeholder="Search tx hash or description..."
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") updateParams({ q: searchDraft || null, page: null }); }}
          onBlur={() => { if (searchDraft !== search) updateParams({ q: searchDraft || null, page: null }); }}
          className="rounded px-2 py-1 text-sm flex-1 max-w-xs"
        />
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => updateParams({ from: e.target.value || null, page: null })}
          className="rounded px-2 py-1 text-sm"
          style={{
            backgroundColor: "var(--bg-surface)",
            color: "var(--text-primary)",
            border: "1px solid var(--border-default)",
          }}
          title="From date"
        />
        <span style={{ color: "var(--text-muted)", alignSelf: "center" }}>&ndash;</span>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => updateParams({ to: e.target.value || null, page: null })}
          className="rounded px-2 py-1 text-sm"
          style={{
            backgroundColor: "var(--bg-surface)",
            color: "var(--text-primary)",
            border: "1px solid var(--border-default)",
          }}
          title="To date"
        />
        {(dateFrom || dateTo) && (
          <button
            onClick={() => updateParams({ from: null, to: null, page: null })}
            className="text-xs px-2 py-1 rounded transition-colors"
            style={{ color: "var(--accent)" }}
            title="Clear date filter"
          >
            Clear dates
          </button>
        )}
        {errorCount > 0 && (
          <button
            onClick={() => updateParams({ has_errors: !showErrors ? "true" : null, page: null })}
            className="rounded px-3 py-1 text-sm font-medium transition-colors"
            style={{
              backgroundColor: showErrors ? "var(--danger)" : "var(--bg-surface)",
              color: showErrors ? "#fff" : "var(--danger)",
              border: `1px solid ${showErrors ? "var(--danger)" : "var(--border-default)"}`,
            }}
          >
            Errors ({errorCount})
          </button>
        )}
      </div>

      {loading && <LoadingSpinner />}
      {error && <ErrorBanner message={error} onRetry={load} />}
      {!loading && !error && txns.length === 0 && (
        <EmptyState title="No transactions" actionLabel="Import CSV" actionTo="/import" />
      )}
      {!loading && !error && txns.length > 0 && (
        <>
          <div className="space-y-6" style={{ paddingBottom: 56 }}>
            {dateGroups.map(([dateLabel, dateTxns]) => (
              <div key={dateLabel}>
                <div
                  className="text-xs font-semibold uppercase tracking-wider mb-2 px-1"
                  style={{ color: "var(--text-muted)" }}
                >
                  {dateLabel}
                </div>
                <div
                  className="glass-card overflow-hidden divide-y"
                  style={{ borderColor: "var(--border-subtle)" }}
                >
                  {dateTxns.map((tx) => (
                    <div key={tx.id} style={{ borderColor: "var(--border-subtle)" }}>
                      <TransactionCard tx={tx} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <StickyPagination
            page={page}
            totalPages={totalPages}
            total={total}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
