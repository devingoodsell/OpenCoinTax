import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  fetchWallets,
  createWallet,
  deleteWallet,
  type WalletListItem,
} from "../../api/client";
import LoadingSpinner from "../../components/LoadingSpinner";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import WalletCard, { WALLET_TYPES, CategoryBadge } from "./WalletCard";

export default function Wallets() {
  const navigate = useNavigate();
  const [wallets, setWallets] = useState<WalletListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [showArchived, setShowArchived] = useState(false);

  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState("");
  const [formType, setFormType] = useState("exchange");
  const [formProvider, setFormProvider] = useState("");
  const [formNotes, setFormNotes] = useState("");
  const [creating, setCreating] = useState(false);

  const [deleteId, setDeleteId] = useState<number | null>(null);

  function load() {
    setLoading(true);
    setError("");
    fetchWallets({
      search: search || undefined,
      sort_by: sortBy,
      sort_dir: sortDir,
      include_archived: showArchived || undefined,
    })
      .then((r) => setWallets(Array.isArray(r.data) ? r.data : (r.data as any).items || []))
      .catch((e) => setError(e.response?.data?.detail || "Failed to load"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, [search, sortBy, sortDir, showArchived]);

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    createWallet({
      name: formName,
      type: formType,
      provider: formProvider || undefined,
      notes: formNotes || undefined,
    })
      .then((r) => {
        setShowForm(false);
        setFormName("");
        setFormProvider("");
        setFormNotes("");
        navigate(`/wallets/${r.data.id}`);
      })
      .catch((err) => setError(err.response?.data?.detail || "Create failed"))
      .finally(() => setCreating(false));
  }

  function handleDelete() {
    if (!deleteId) return;
    deleteWallet(deleteId)
      .then(() => {
        setDeleteId(null);
        load();
      })
      .catch((err) => setError(err.response?.data?.detail || "Delete failed"));
  }

  if (loading && wallets.length === 0) return <LoadingSpinner />;

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>Wallets & Exchanges</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-3 py-1.5 rounded text-sm transition-colors cursor-pointer"
          style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
        >
          {showForm ? "Cancel" : "Add Wallet/Exchange"}
        </button>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {/* Create form */}
      {showForm && (
        <form onSubmit={handleCreate} className="glass-card p-4 mb-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs block mb-1" style={{ color: "var(--text-muted)" }}>Name</label>
              <input
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                required
                placeholder="e.g. Coinbase, Ledger Nano"
                className="rounded px-2 py-1.5 text-sm w-full"
              />
            </div>
            <div>
              <label className="text-xs block mb-1" style={{ color: "var(--text-muted)" }}>Type</label>
              <select
                value={formType}
                onChange={(e) => setFormType(e.target.value)}
                className="rounded px-2 py-1.5 text-sm w-full"
              >
                {WALLET_TYPES.map((t) => (
                  <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs block mb-1" style={{ color: "var(--text-muted)" }}>Provider (optional)</label>
              <input
                value={formProvider}
                onChange={(e) => setFormProvider(e.target.value)}
                placeholder="e.g. coinbase, ledger"
                className="rounded px-2 py-1.5 text-sm w-full"
              />
            </div>
            <div>
              <label className="text-xs block mb-1" style={{ color: "var(--text-muted)" }}>Notes (optional)</label>
              <input
                value={formNotes}
                onChange={(e) => setFormNotes(e.target.value)}
                placeholder="Any notes..."
                className="rounded px-2 py-1.5 text-sm w-full"
              />
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
            Category auto-derived:{" "}
            <CategoryBadge category={formType === "exchange" ? "exchange" : "wallet"} />
          </div>
          <button
            type="submit"
            disabled={creating}
            className="px-4 py-1.5 rounded text-sm disabled:opacity-50 transition-colors cursor-pointer"
            style={{ border: "1px solid var(--success)", color: "var(--success)" }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--success)"; e.currentTarget.style.color = "#fff"; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--success)"; }}
          >
            {creating ? "Creating..." : "Create"}
          </button>
        </form>
      )}

      {/* Search / sort / archive bar */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search wallets..."
          className="rounded px-3 py-1.5 text-sm w-56"
        />
        <select
          value={`${sortBy}:${sortDir}`}
          onChange={(e) => {
            const [s, d] = e.target.value.split(":");
            setSortBy(s);
            setSortDir(d as "asc" | "desc");
          }}
          className="rounded px-2 py-1.5 text-sm"
        >
          <option value="name:asc">Name A-Z</option>
          <option value="name:desc">Name Z-A</option>
          <option value="created_at:desc">Newest first</option>
          <option value="created_at:asc">Oldest first</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm cursor-pointer" style={{ color: "var(--text-secondary)" }}>
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
            className="rounded"
          />
          Show archived
        </label>
      </div>

      {/* Wallet grid */}
      {wallets.length === 0 ? (
        <EmptyState
          title="No wallets or exchanges"
          description='Click "Add Wallet/Exchange" to get started.'
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {wallets.map((w) => (
            <WalletCard
              key={w.id}
              wallet={w}
              onReload={load}
              onDelete={setDeleteId}
              setError={setError}
            />
          ))}
        </div>
      )}

      {/* Delete confirmation modal */}
      {deleteId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="glass-card p-6 max-w-sm mx-4" style={{ background: "var(--bg-elevated)" }}>
            <h3 className="font-semibold mb-2" style={{ color: "var(--text-primary)" }}>Delete wallet?</h3>
            <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
              This will permanently delete the wallet and all its accounts.
              Transactions will be preserved but unlinked.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setDeleteId(null)}
                className="px-3 py-1.5 rounded text-sm"
                style={{ backgroundColor: "var(--bg-surface-hover)", color: "var(--text-secondary)" }}
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="px-3 py-1.5 rounded text-sm transition-colors cursor-pointer"
                style={{ border: "1px solid var(--danger)", color: "var(--danger)" }}
                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--danger)"; e.currentTarget.style.color = "#fff"; }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--danger)"; }}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
