import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { fetchTransaction, deleteTransaction, updateTransaction } from "../../api/client";
import LoadingSpinner from "../../components/LoadingSpinner";
import ErrorBanner from "../../components/ErrorBanner";
import { SummaryHeader, DetailsTab, truncateHash, type TxDetail } from "./TransactionInfo";
import { LedgerTab, CostAnalysisTab } from "./LotAssignments";
import { TabBar, EditMode, type EditFormState } from "./WhatIfAnalysis";

type TabId = "details" | "ledger" | "cost";

export default function TransactionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [tx, setTx] = useState<TxDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [tab, setTab] = useState<TabId>("details");
  const [editForm, setEditForm] = useState<EditFormState>({
    type: "", from_amount: "", to_amount: "", from_value_usd: "", to_value_usd: "", label: "",
  });

  function loadTx() {
    if (!id) return;
    setLoading(true);
    fetchTransaction(Number(id))
      .then((r) => {
        setTx(r.data);
        setEditForm({
          type: r.data.type,
          from_amount: r.data.from_amount ?? "",
          to_amount: r.data.to_amount ?? "",
          from_value_usd: r.data.from_value_usd ?? "",
          to_value_usd: r.data.to_value_usd ?? "",
          label: r.data.label ?? "",
        });
      })
      .catch((e) => setError(e.response?.data?.detail || "Not found"))
      .finally(() => setLoading(false));
  }

  useEffect(() => { loadTx(); }, [id]);

  function handleDelete() {
    if (!tx || !confirm("Delete this transaction? This cannot be undone.")) return;
    deleteTransaction(tx.id)
      .then(() => navigate("/transactions"))
      .catch((e) => setError(e.response?.data?.detail || "Delete failed"));
  }

  function handleSave() {
    if (!tx) return;
    const data: Record<string, unknown> = {};
    if (editForm.type !== tx.type) data.type = editForm.type;
    if (editForm.from_amount !== (tx.from_amount ?? "")) data.from_amount = editForm.from_amount || null;
    if (editForm.to_amount !== (tx.to_amount ?? "")) data.to_amount = editForm.to_amount || null;
    if (editForm.from_value_usd !== (tx.from_value_usd ?? "")) data.from_value_usd = editForm.from_value_usd || null;
    if (editForm.to_value_usd !== (tx.to_value_usd ?? "")) data.to_value_usd = editForm.to_value_usd || null;
    if (editForm.label !== (tx.label ?? "")) data.label = editForm.label || null;
    updateTransaction(tx.id, data)
      .then(() => { setEditing(false); setSaveMsg("Saved. Run tax recalculation from the Reports page to re-process."); loadTx(); })
      .catch((e) => setError(e.response?.data?.detail || "Save failed"));
  }

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorBanner message={error} />;
  if (!tx) return null;

  const truncatedHash = tx.tx_hash ? truncateHash(tx.tx_hash) : null;

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-4">
        <Link to="/transactions" className="text-sm hover:underline" style={{ color: "var(--text-secondary)" }}>&larr; Transactions</Link>
        <div className="flex items-center gap-3">
          {truncatedHash && <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>#{truncatedHash}</span>}
          {!editing && (
            <button onClick={() => { setEditing(true); setSaveMsg(""); }} className="p-1.5 rounded transition-colors" style={{ color: "var(--text-secondary)", border: "1px solid var(--border-default)" }} title="Edit transaction">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
            </button>
          )}
          <button onClick={handleDelete} className="p-1.5 rounded transition-colors" style={{ color: "var(--danger)", border: "1px solid rgba(239,68,68,0.3)" }} title="Delete transaction">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
          </button>
        </div>
      </div>

      {tx.has_tax_error && (
        <div className="mb-4 p-4 rounded-lg" style={{ backgroundColor: "rgba(239, 68, 68, 0.08)", borderLeft: "4px solid var(--danger)", color: "var(--text-primary)" }}>
          <div className="flex items-center justify-between">
            <div>
              <div className="font-semibold text-sm" style={{ color: "var(--danger)" }}>Tax Calculation Error</div>
              <div className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>{tx.tax_error}</div>
            </div>
            {!editing && <button onClick={() => { setEditing(true); setSaveMsg(""); }} className="px-3 py-1 rounded text-sm transition-colors" style={{ backgroundColor: "var(--danger)", color: "#fff" }}>Edit to Fix</button>}
          </div>
        </div>
      )}

      {saveMsg && <div className="mb-4 p-3 rounded-lg text-sm" style={{ backgroundColor: "rgba(34, 197, 94, 0.08)", borderLeft: "4px solid var(--success)", color: "var(--text-secondary)" }}>{saveMsg}</div>}

      <SummaryHeader tx={tx} />

      <div className="glass-card overflow-hidden" style={{ borderRadius: "0 0 12px 12px" }}>
        {editing ? (
          <>
            <div className="px-5 py-2.5 text-sm font-medium" style={{ color: "var(--accent)", borderBottom: "1px solid var(--border-default)" }}>Editing Transaction</div>
            <EditMode tx={tx} editForm={editForm} setEditForm={setEditForm} onSave={handleSave} onCancel={() => setEditing(false)} />
          </>
        ) : (
          <>
            <TabBar active={tab} onChange={setTab} />
            {tab === "details" && <DetailsTab tx={tx} />}
            {tab === "ledger" && <LedgerTab tx={tx} />}
            {tab === "cost" && <CostAnalysisTab tx={tx} />}
          </>
        )}
      </div>
    </div>
  );
}
