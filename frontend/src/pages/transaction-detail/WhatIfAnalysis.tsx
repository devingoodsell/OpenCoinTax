import type { TxDetail } from "./TransactionInfo";

const TX_TYPES = [
  "buy", "sell", "trade", "transfer", "deposit", "withdrawal",
  "staking_reward", "airdrop", "mining", "interest", "gift_received",
  "gift_sent", "cost", "fork",
];

type TabId = "details" | "ledger" | "cost";

function EditField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 py-3" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
      <span className="text-xs w-36 flex-shrink-0" style={{ color: "var(--text-muted)" }}>{label}</span>
      <div className="flex items-center">{children}</div>
    </div>
  );
}

export interface EditFormState {
  type: string;
  from_amount: string;
  to_amount: string;
  from_value_usd: string;
  to_value_usd: string;
  label: string;
}

export function TabBar({ active, onChange }: { active: TabId; onChange: (tab: TabId) => void }) {
  const tabs: { id: TabId; label: string }[] = [
    { id: "details", label: "Details" },
    { id: "ledger", label: "Ledger" },
    { id: "cost", label: "Cost analysis" },
  ];
  return (
    <div className="flex gap-0" style={{ backgroundColor: "var(--bg-surface)", borderBottom: "1px solid var(--border-default)" }}>
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)} className="px-5 py-2.5 text-sm font-medium transition-colors relative" style={{ color: active === t.id ? "var(--accent)" : "var(--text-muted)", backgroundColor: "transparent", border: "none", cursor: "pointer" }}>
          {t.label}
          {active === t.id && <div className="absolute bottom-0 left-0 right-0 h-0.5" style={{ backgroundColor: "var(--accent)" }} />}
        </button>
      ))}
    </div>
  );
}

export function EditMode({
  tx,
  editForm,
  setEditForm,
  onSave,
  onCancel,
}: {
  tx: TxDetail;
  editForm: EditFormState;
  setEditForm: (f: EditFormState) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const inputStyle = { backgroundColor: "var(--bg-base)", color: "var(--text-primary)", border: "1px solid var(--border-default)" };

  return (
    <div className="p-5 space-y-0">
      <EditField label="Type">
        <select value={editForm.type} onChange={(e) => setEditForm({ ...editForm, type: e.target.value })} className="rounded px-2 py-1.5 text-sm" style={inputStyle}>
          {TX_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </EditField>
      <EditField label="Sent Amount">
        <input value={editForm.from_amount} onChange={(e) => setEditForm({ ...editForm, from_amount: e.target.value })} className="rounded px-2 py-1.5 text-sm w-48" style={inputStyle} placeholder="0.00" />
        {tx.from_asset_symbol && <span className="text-xs ml-2" style={{ color: "var(--text-muted)" }}>{tx.from_asset_symbol}</span>}
      </EditField>
      <EditField label="Received Amount">
        <input value={editForm.to_amount} onChange={(e) => setEditForm({ ...editForm, to_amount: e.target.value })} className="rounded px-2 py-1.5 text-sm w-48" style={inputStyle} placeholder="0.00" />
        {tx.to_asset_symbol && <span className="text-xs ml-2" style={{ color: "var(--text-muted)" }}>{tx.to_asset_symbol}</span>}
      </EditField>
      <EditField label="Sent USD Value">
        <input value={editForm.from_value_usd} onChange={(e) => setEditForm({ ...editForm, from_value_usd: e.target.value })} className="rounded px-2 py-1.5 text-sm w-48" style={inputStyle} placeholder="$0.00" />
      </EditField>
      <EditField label="Received USD Value">
        <input value={editForm.to_value_usd} onChange={(e) => setEditForm({ ...editForm, to_value_usd: e.target.value })} className="rounded px-2 py-1.5 text-sm w-48" style={inputStyle} placeholder="$0.00" />
      </EditField>
      <EditField label="Label">
        <input value={editForm.label} onChange={(e) => setEditForm({ ...editForm, label: e.target.value })} className="rounded px-2 py-1.5 text-sm w-48" style={inputStyle} placeholder="Label" />
      </EditField>
      <div className="flex gap-2 pt-4">
        <button onClick={onSave} className="px-4 py-1.5 rounded text-sm font-medium transition-colors" style={{ backgroundColor: "var(--accent)", color: "#fff" }}>Save</button>
        <button onClick={onCancel} className="px-4 py-1.5 rounded text-sm transition-colors" style={{ color: "var(--text-secondary)", border: "1px solid var(--border-default)" }}>Cancel</button>
      </div>
    </div>
  );
}
