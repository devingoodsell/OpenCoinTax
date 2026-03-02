import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  fetchWallet,
  updateWallet,
  type WalletDetail as WalletDetailType,
} from "../../api/client";
import LoadingSpinner from "../../components/LoadingSpinner";
import ErrorBanner from "../../components/ErrorBanner";
import WalletTransactionSummary from "./WalletTransactions";
import WalletAccounts from "./WalletAccounts";
import WalletHoldings from "./WalletHoldings";
import WalletImportSync from "./WalletCostBasis";

export default function WalletDetail() {
  const { id } = useParams<{ id: string }>();
  const [wallet, setWallet] = useState<WalletDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"accounts" | "holdings" | "import">("holdings");
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesValue, setNotesValue] = useState("");

  function loadWallet() {
    if (!id) return;
    setLoading(true);
    fetchWallet(Number(id))
      .then((r) => {
        setWallet(r.data);
        if (r.data.accounts && r.data.accounts.length > 0) {
          setTab("accounts");
        } else {
          setTab("holdings");
        }
      })
      .catch((e) => setError(e.response?.data?.detail || "Not found"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadWallet();
  }, [id]);

  async function handleSaveNotes() {
    if (!wallet) return;
    try {
      await updateWallet(wallet.id, { notes: notesValue || null });
      setEditingNotes(false);
      loadWallet();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Save notes failed");
    }
  }

  if (loading) return <LoadingSpinner />;
  if (error && !wallet) return <ErrorBanner message={error} />;
  if (!wallet) return null;

  const isExchange = wallet.category === "exchange";

  return (
    <div className="max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <Link to="/wallets" className="text-xs hover:underline" style={{ color: "var(--text-muted)" }}>&larr; All Wallets</Link>
          <h1 className="text-2xl font-bold flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
            {wallet.name}
            <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded" style={{
              background: isExchange ? "rgba(168, 85, 247, 0.15)" : "rgba(59, 130, 246, 0.15)",
              color: isExchange ? "#c084fc" : "#60a5fa",
            }}>
              {isExchange ? "Exchange" : "Wallet"}
            </span>
          </h1>
        </div>
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
          {wallet.type}{wallet.provider ? ` \u00B7 ${wallet.provider}` : ""}
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={() => setError("")} />}

      <WalletTransactionSummary summary={wallet.transaction_summary} walletId={wallet.id} />

      {/* Tabs */}
      <div className="mb-4" style={{ borderBottom: "1px solid var(--border-default)" }}>
        <nav className="flex gap-4 -mb-px">
          <button onClick={() => setTab("accounts")} className="pb-2 text-sm" style={{
            borderBottom: tab === "accounts" ? "2px solid var(--accent)" : "2px solid transparent",
            color: tab === "accounts" ? "var(--accent)" : "var(--text-muted)",
          }}>
            Accounts ({wallet.accounts.length})
          </button>
          <button onClick={() => setTab("holdings")} className="pb-2 text-sm" style={{
            borderBottom: tab === "holdings" ? "2px solid var(--accent)" : "2px solid transparent",
            color: tab === "holdings" ? "var(--accent)" : "var(--text-muted)",
          }}>
            Holdings
          </button>
          {isExchange && (
            <button onClick={() => setTab("import")} className="pb-2 text-sm" style={{
              borderBottom: tab === "import" ? "2px solid var(--accent)" : "2px solid transparent",
              color: tab === "import" ? "var(--accent)" : "var(--text-muted)",
            }}>
              Import / Sync
            </button>
          )}
        </nav>
      </div>

      {tab === "accounts" && <WalletAccounts wallet={wallet} loadWallet={loadWallet} setError={setError} />}
      {tab === "holdings" && <WalletHoldings wallet={wallet} setWallet={setWallet} setError={setError} loadWallet={loadWallet} />}
      {tab === "import" && isExchange && <WalletImportSync wallet={wallet} loadWallet={loadWallet} setError={setError} />}

      {/* Notes section */}
      <div className="mt-6 glass-card p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>Notes</h3>
          {!editingNotes && (
            <button onClick={() => { setEditingNotes(true); setNotesValue(wallet.notes || ""); }} className="text-xs hover:underline" style={{ color: "var(--accent)" }}>Edit</button>
          )}
        </div>
        {editingNotes ? (
          <div className="space-y-2">
            <textarea value={notesValue} onChange={(e) => setNotesValue(e.target.value)} rows={3} className="rounded px-2 py-1.5 text-sm w-full" placeholder="Add notes about this wallet..." />
            <div className="flex gap-2">
              <button onClick={handleSaveNotes} className="px-3 py-1 text-white rounded text-xs" style={{ backgroundColor: "var(--success)" }}>Save</button>
              <button onClick={() => setEditingNotes(false)} className="px-3 py-1 rounded text-xs" style={{ backgroundColor: "var(--bg-surface-hover)", color: "var(--text-secondary)" }}>Cancel</button>
            </div>
          </div>
        ) : (
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{wallet.notes || "No notes."}</p>
        )}
      </div>

      {!isExchange && (
        <div className="mt-4">
          <Link to={`/import?wallet=${wallet.id}`} className="text-sm hover:underline" style={{ color: "var(--accent)" }}>
            Import transactions for this wallet &rarr;
          </Link>
        </div>
      )}
    </div>
  );
}
