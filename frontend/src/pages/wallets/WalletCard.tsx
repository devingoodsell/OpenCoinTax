import { useState } from "react";
import { Link } from "react-router-dom";
import { updateWallet, type WalletListItem } from "../../api/client";
import DropdownMenu from "../../components/DropdownMenu";

export const WALLET_TYPES = ["exchange", "hardware", "software", "defi", "other"];

export function CategoryBadge({ category }: { category: string }) {
  const isExchange = category === "exchange";
  return (
    <span
      className="inline-block text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded"
      style={{
        background: isExchange ? "rgba(168, 85, 247, 0.15)" : "rgba(59, 130, 246, 0.15)",
        color: isExchange ? "#c084fc" : "#60a5fa",
      }}
    >
      {isExchange ? "Exchange" : "Wallet"}
    </span>
  );
}

export default function WalletCard({
  wallet: w,
  onReload,
  onDelete,
  setError,
}: {
  wallet: WalletListItem;
  onReload: () => void;
  onDelete: (id: number) => void;
  setError: (msg: string) => void;
}) {
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editType, setEditType] = useState("");
  const [editProvider, setEditProvider] = useState("");
  const [editNotes, setEditNotes] = useState("");

  function startEdit() {
    setEditId(w.id);
    setEditName(w.name);
    setEditType(w.type);
    setEditProvider(w.provider || "");
    setEditNotes(w.notes || "");
  }

  function handleUpdate(e: React.FormEvent) {
    e.preventDefault();
    if (!editId) return;
    updateWallet(editId, {
      name: editName,
      type: editType,
      provider: editProvider || null,
      notes: editNotes || null,
    })
      .then(() => {
        setEditId(null);
        onReload();
      })
      .catch((err) => setError(err.response?.data?.detail || "Update failed"));
  }

  function handleArchive() {
    updateWallet(w.id, { is_archived: !w.is_archived })
      .then(() => onReload())
      .catch((err) => setError(err.response?.data?.detail || "Archive failed"));
  }

  return (
    <div
      className={`glass-card transition-all relative ${w.is_archived ? "opacity-60" : ""}`}
      style={{ borderColor: "var(--border-subtle)" }}
    >
      {editId === w.id ? (
        <form onSubmit={handleUpdate} className="p-4 space-y-2">
          <input
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            required
            className="rounded px-2 py-1 text-sm w-full"
          />
          <select
            value={editType}
            onChange={(e) => setEditType(e.target.value)}
            className="rounded px-2 py-1 text-sm w-full"
          >
            {WALLET_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input
            value={editProvider}
            onChange={(e) => setEditProvider(e.target.value)}
            placeholder="Provider"
            className="rounded px-2 py-1 text-sm w-full"
          />
          <input
            value={editNotes}
            onChange={(e) => setEditNotes(e.target.value)}
            placeholder="Notes"
            className="rounded px-2 py-1 text-sm w-full"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              className="px-3 py-1 rounded text-xs transition-colors cursor-pointer"
              style={{ border: "1px solid var(--success)", color: "var(--success)" }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--success)"; e.currentTarget.style.color = "#fff"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--success)"; }}
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => setEditId(null)}
              className="px-3 py-1 rounded text-xs"
              style={{ backgroundColor: "var(--bg-surface-hover)", color: "var(--text-secondary)" }}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="p-4">
          <div className="flex items-start justify-between gap-2 mb-1">
            <Link to={`/wallets/${w.id}`} className="flex-1 min-w-0">
              <span className="font-medium" style={{ color: "var(--text-primary)" }}>{w.name}</span>
            </Link>
            <div className="flex items-center gap-1.5 shrink-0">
              <CategoryBadge category={w.category} />
              <DropdownMenu
                items={[
                  { label: "Edit", onClick: startEdit },
                  { label: w.is_archived ? "Unarchive" : "Archive", onClick: handleArchive },
                  { label: "Delete", onClick: () => onDelete(w.id), variant: "danger" },
                ]}
              />
            </div>
          </div>
          <Link to={`/wallets/${w.id}`} className="block">
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              {w.type}
              {w.provider ? ` \u00B7 ${w.provider}` : ""}
            </div>
            <div className="flex gap-4 mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
              {w.account_count > 0 && (
                <span>{w.account_count} account{w.account_count !== 1 ? "s" : ""}</span>
              )}
              <span>{w.transaction_count} txn{w.transaction_count !== 1 ? "s" : ""}</span>
            </div>
            {(w.total_value_usd || w.total_cost_basis_usd) && (
              <div className="flex gap-4 mt-2 text-xs">
                {w.total_value_usd && Number(w.total_value_usd) > 0 && (
                  <span>
                    <span style={{ color: "var(--text-muted)" }}>Market </span>
                    <span style={{ color: "var(--success)" }}>
                      ${Number(w.total_value_usd).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </span>
                  </span>
                )}
                {w.total_cost_basis_usd && Number(w.total_cost_basis_usd) > 0 && (
                  <span>
                    <span style={{ color: "var(--text-muted)" }}>Cost </span>
                    <span style={{ color: "var(--text-secondary)" }}>
                      ${Number(w.total_cost_basis_usd).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </span>
                  </span>
                )}
              </div>
            )}
            {w.is_archived && (
              <span className="text-[10px] mt-1 inline-block" style={{ color: "var(--warning)" }}>
                Archived
              </span>
            )}
          </Link>
        </div>
      )}
    </div>
  );
}
