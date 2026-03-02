import { useState } from "react";
import { getTypeConfig, formatAmount, formatUsd, TypeBadge } from "../../utils/transactionHelpers";

export interface TxDetail {
  id: number;
  datetime_utc: string;
  type: string;
  from_amount: string | null;
  from_asset_symbol: string | null;
  to_amount: string | null;
  to_asset_symbol: string | null;
  fee_amount: string | null;
  fee_asset_symbol: string | null;
  fee_value_usd: string | null;
  from_value_usd: string | null;
  to_value_usd: string | null;
  net_value_usd: string | null;
  from_wallet_name: string | null;
  to_wallet_name: string | null;
  from_account_name: string | null;
  to_account_name: string | null;
  label: string | null;
  description: string | null;
  tx_hash: string | null;
  source: string;
  has_tax_error: boolean;
  tax_error: string | null;
  lot_assignments: LotAssignment[];
}

export interface LotAssignment {
  id: number;
  amount: string;
  cost_basis_usd: string;
  proceeds_usd: string;
  gain_loss_usd: string;
  holding_period: string;
}

export function truncateHash(hash: string): string {
  if (hash.length <= 14) return hash;
  return `${hash.slice(0, 6)}...${hash.slice(-5)}`;
}

export function walletLabel(walletName: string | null, accountName: string | null): string {
  return [walletName, accountName].filter(Boolean).join(" \u203A ");
}

export function computeTotals(assignments: LotAssignment[]) {
  let totalCost = 0, totalProceeds = 0, totalGain = 0, shortTermGain = 0, longTermGain = 0;
  for (const a of assignments) {
    totalCost += parseFloat(a.cost_basis_usd) || 0;
    totalProceeds += parseFloat(a.proceeds_usd) || 0;
    const gl = parseFloat(a.gain_loss_usd) || 0;
    totalGain += gl;
    if (a.holding_period === "long_term") longTermGain += gl;
    else shortTermGain += gl;
  }
  return { totalCost, totalProceeds, totalGain, shortTermGain, longTermGain };
}

function feePercentage(feeUsd: string | null, valueUsd: string | null): string | null {
  if (!feeUsd || !valueUsd) return null;
  const fee = parseFloat(feeUsd);
  const val = parseFloat(valueUsd);
  if (!val || !fee) return null;
  const pct = (fee / val) * 100;
  if (pct < 0.01) return "< 0.01%";
  return `${pct.toFixed(2)}%`;
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).catch(() => {});
}

function FlowRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2.5" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
      <span className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</span>
      <span className="text-sm" style={{ color: "var(--text-primary)" }}>{value}</span>
    </div>
  );
}

export function SummaryHeader({ tx }: { tx: TxDetail }) {
  const cfg = getTypeConfig(tx.type);
  const time = new Date(tx.datetime_utc).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true });
  const fromWallet = walletLabel(tx.from_wallet_name, tx.from_account_name);
  const toWallet = walletLabel(tx.to_wallet_name, tx.to_account_name);
  const hasFrom = !!tx.from_amount;
  const hasTo = !!tx.to_amount;
  const totals = tx.lot_assignments.length > 0 ? computeTotals(tx.lot_assignments) : null;
  const feePct = feePercentage(tx.fee_value_usd, tx.net_value_usd || tx.from_value_usd);

  return (
    <div className="glass-card p-5 mb-1" style={{ borderBottom: "none", borderRadius: "12px 12px 0 0" }}>
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-3 flex-shrink-0">
          <TypeBadge type={tx.type} />
          <div>
            <div className="text-base font-semibold" style={{ color: cfg.color }}>{cfg.label}</div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>{time}</div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 flex-1 min-w-0 justify-center">
          {hasFrom && (
            <div className="text-center min-w-0">
              <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}><span style={{ color: "var(--danger)" }}>&minus;</span> {formatAmount(tx.from_amount)} <span style={{ color: "var(--text-secondary)" }}>{tx.from_asset_symbol}</span></div>
              {fromWallet && <div className="text-xs truncate max-w-48" style={{ color: "var(--text-muted)" }}>{fromWallet}</div>}
              {tx.from_value_usd && <div className="text-xs" style={{ color: "var(--text-muted)" }}>~{formatUsd(tx.from_value_usd)} cost</div>}
            </div>
          )}
          {hasFrom && hasTo && <div className="text-xl font-bold flex-shrink-0" style={{ color: cfg.color }}>&raquo;</div>}
          {hasTo && (
            <div className="text-center min-w-0">
              <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}><span style={{ color: "var(--success)" }}>+</span> {formatAmount(tx.to_amount)} <span style={{ color: "var(--text-secondary)" }}>{tx.to_asset_symbol}</span></div>
              {toWallet && <div className="text-xs truncate max-w-48" style={{ color: "var(--text-muted)" }}>{toWallet}</div>}
              {tx.to_value_usd && <div className="text-xs" style={{ color: "var(--text-muted)" }}>~{formatUsd(tx.to_value_usd)}</div>}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {totals && totals.totalGain !== 0 && (
            <span className="text-sm font-semibold" style={{ color: totals.totalGain >= 0 ? "var(--success)" : "var(--danger)" }}>{totals.totalGain >= 0 ? "+" : ""}{formatUsd(totals.totalGain.toFixed(2))}</span>
          )}
          {tx.label && <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ backgroundColor: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border-default)" }}>{tx.label}</span>}
          {feePct && <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ backgroundColor: "rgba(217,119,6,0.1)", color: "#d97706", border: "1px solid rgba(217,119,6,0.2)" }}>{feePct} fee</span>}
        </div>
      </div>
    </div>
  );
}

export function DetailsTab({ tx }: { tx: TxDetail }) {
  const [copied, setCopied] = useState(false);
  const fromWallet = walletLabel(tx.from_wallet_name, tx.from_account_name);
  const toWallet = walletLabel(tx.to_wallet_name, tx.to_account_name);
  const totals = tx.lot_assignments.length > 0 ? computeTotals(tx.lot_assignments) : null;

  function handleCopyHash() {
    if (!tx.tx_hash) return;
    copyToClipboard(tx.tx_hash);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="flex flex-col md:flex-row gap-6 p-5">
      <div className="flex-1 min-w-0 space-y-4">
        <div>
          <div className="text-xs font-medium mb-1" style={{ color: "var(--text-muted)" }}>Tx Hash</div>
          {tx.tx_hash ? (
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm" style={{ color: "var(--text-primary)" }}>{truncateHash(tx.tx_hash)}</span>
              <button onClick={handleCopyHash} className="text-xs px-1.5 py-0.5 rounded transition-colors" style={{ color: copied ? "var(--success)" : "var(--text-muted)", backgroundColor: "var(--bg-surface)", border: "1px solid var(--border-subtle)" }} title="Copy full hash">{copied ? "Copied" : "Copy"}</button>
            </div>
          ) : <span className="text-sm" style={{ color: "var(--text-muted)" }}>&mdash;</span>}
        </div>
        <div>
          <div className="text-xs font-medium mb-1" style={{ color: "var(--text-muted)" }}>Function</div>
          <span className="text-sm" style={{ color: "var(--text-primary)" }}>{tx.label || "\u2014"}</span>
        </div>
        <div>
          <div className="text-xs font-medium mb-1" style={{ color: "var(--text-muted)" }}>Source</div>
          <span className="text-sm" style={{ color: "var(--text-primary)" }}>{tx.source}</span>
        </div>
        {tx.description && (
          <div>
            <div className="text-xs font-medium mb-1" style={{ color: "var(--text-muted)" }}>Description</div>
            <span className="text-sm" style={{ color: "var(--text-secondary)" }}>{tx.description}</span>
          </div>
        )}
      </div>
      <div className="flex-1 min-w-0 rounded-lg p-4 space-y-0" style={{ backgroundColor: "var(--bg-surface)", border: "1px solid var(--border-default)" }}>
        {tx.from_amount && (
          <div className="flex items-center justify-between py-2.5" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm font-semibold" style={{ color: "var(--danger)" }}>&minus;</span>
              <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{formatAmount(tx.from_amount)} {tx.from_asset_symbol}</span>
            </div>
            {fromWallet && <span className="text-xs truncate max-w-40" style={{ color: "var(--text-muted)" }}>{fromWallet}</span>}
          </div>
        )}
        {tx.to_amount && (
          <div className="flex items-center justify-between py-2.5" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm font-semibold" style={{ color: "var(--success)" }}>+</span>
              <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{formatAmount(tx.to_amount)} {tx.to_asset_symbol}</span>
            </div>
            {toWallet && <span className="text-xs truncate max-w-40" style={{ color: "var(--text-muted)" }}>{toWallet}</span>}
          </div>
        )}
        {tx.net_value_usd && <FlowRow label="Fiat value" value={formatUsd(tx.net_value_usd)} />}
        {tx.fee_amount && (
          <FlowRow label="Fee" value={<>{tx.fee_value_usd && <span style={{ color: "var(--text-muted)" }}>{formatUsd(tx.fee_value_usd)} </span>}<span style={{ color: "var(--text-primary)" }}>{formatAmount(tx.fee_amount)} {tx.fee_asset_symbol}</span></>} />
        )}
        {totals && <FlowRow label="Cost basis" value={formatUsd(totals.totalCost.toFixed(2))} />}
        {totals && (
          <div className="flex items-center justify-between py-2.5">
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>Gain</span>
            <span className="text-sm font-semibold" style={{ color: totals.totalGain >= 0 ? "var(--success)" : "var(--danger)" }}>{totals.totalGain >= 0 ? "+" : ""}{formatUsd(totals.totalGain.toFixed(2))}</span>
          </div>
        )}
      </div>
    </div>
  );
}
