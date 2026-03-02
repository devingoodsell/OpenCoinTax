import { useState } from "react";
import { Link } from "react-router-dom";
import { getTypeConfig, formatAmount, formatUsd, TypeBadge } from "../../utils/transactionHelpers";

export interface Transaction {
  id: number;
  datetime_utc: string;
  type: string;
  from_amount: string | null;
  from_asset_symbol: string | null;
  from_wallet_name: string | null;
  from_account_name: string | null;
  to_amount: string | null;
  to_asset_symbol: string | null;
  to_wallet_name: string | null;
  to_account_name: string | null;
  fee_amount: string | null;
  fee_asset_symbol: string | null;
  net_value_usd: string | null;
  from_value_usd: string | null;
  to_value_usd: string | null;
  label: string | null;
  description: string | null;
  tx_hash: string | null;
  has_tax_error: boolean;
  tax_error: string | null;
}

function FlowVisualization({ tx }: { tx: Transaction }) {
  const type = tx.type;
  const fromSym = tx.from_asset_symbol ?? "";
  const toSym = tx.to_asset_symbol ?? "";
  const fromAmt = formatAmount(tx.from_amount);
  const toAmt = formatAmount(tx.to_amount);
  const fromWallet = tx.from_wallet_name || tx.from_account_name || "";
  const toWallet = tx.to_wallet_name || tx.to_account_name || "";

  const twoSided = type === "trade" || type === "transfer";
  const receiveOnly = ["deposit", "staking_reward", "airdrop", "mining", "interest"].includes(type);
  const sendOnly = type === "sell" || type === "withdrawal";
  const isBuy = type === "buy";

  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-1.5 text-sm flex-wrap" style={{ color: "var(--text-primary)" }}>
        {twoSided && (
          <>
            <span className="font-medium">{fromAmt} <span style={{ color: "var(--text-secondary)" }}>{fromSym}</span></span>
            <span style={{ color: "var(--text-muted)" }}>→</span>
            <span className="font-medium">{toAmt} <span style={{ color: "var(--text-secondary)" }}>{toSym}</span></span>
          </>
        )}
        {receiveOnly && (
          <span className="font-medium" style={{ color: "#16a34a" }}>
            + {toAmt} <span style={{ opacity: 0.7 }}>{toSym}</span>
          </span>
        )}
        {sendOnly && (
          <span className="font-medium" style={{ color: "#dc2626" }}>
            − {fromAmt} <span style={{ opacity: 0.7 }}>{fromSym}</span>
          </span>
        )}
        {isBuy && (
          <>
            <span style={{ color: "var(--text-muted)" }}>{fromAmt ? `${fromAmt} USD` : "USD"}</span>
            <span style={{ color: "var(--text-muted)" }}>→</span>
            <span className="font-medium" style={{ color: "#16a34a" }}>
              + {toAmt} <span style={{ opacity: 0.7 }}>{toSym}</span>
            </span>
          </>
        )}
        {!twoSided && !receiveOnly && !sendOnly && !isBuy && (
          <>
            {fromAmt && <span className="font-medium">{fromAmt} {fromSym}</span>}
            {toAmt && <span className="font-medium">{toAmt} {toSym}</span>}
          </>
        )}
      </div>
      {(fromWallet || toWallet) && (
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          {twoSided || isBuy ? (
            <>
              {fromWallet && <span>{fromWallet}</span>}
              {fromWallet && toWallet && <span> → </span>}
              {toWallet && <span>{toWallet}</span>}
            </>
          ) : receiveOnly ? (
            toWallet && <span>{toWallet}</span>
          ) : sendOnly ? (
            fromWallet && <span>{fromWallet}</span>
          ) : (
            <span>{fromWallet || toWallet}</span>
          )}
        </div>
      )}
    </div>
  );
}

function DetailField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</div>
      <div style={{ color: "var(--text-primary)" }}>{children}</div>
    </div>
  );
}

function ExpandedDetail({ tx }: { tx: Transaction }) {
  const cfg = getTypeConfig(tx.type);
  return (
    <div
      className="px-4 pt-3 pb-4"
      style={{ borderTop: "1px solid var(--border-subtle)", backgroundColor: "var(--bg-surface)" }}
    >
      {tx.has_tax_error && (
        <div
          className="mb-3 px-3 py-2 rounded text-sm"
          style={{
            backgroundColor: "rgba(239,68,68,0.1)",
            borderLeft: "3px solid var(--danger)",
            color: "var(--danger)",
          }}
        >
          Tax Error: {tx.tax_error || "Unknown error"}
        </div>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2 text-sm">
        <DetailField label="Type">
          <span style={{ color: cfg.color }}>{cfg.label}</span>
        </DetailField>
        <DetailField label="Date & Time">
          {new Date(tx.datetime_utc).toLocaleString()}
        </DetailField>
        {tx.from_amount && (
          <DetailField label="Sent">
            {formatAmount(tx.from_amount)} {tx.from_asset_symbol ?? ""}
          </DetailField>
        )}
        {tx.to_amount && (
          <DetailField label="Received">
            {formatAmount(tx.to_amount)} {tx.to_asset_symbol ?? ""}
          </DetailField>
        )}
        {tx.from_wallet_name && (
          <DetailField label="From Wallet">{tx.from_wallet_name}</DetailField>
        )}
        {tx.to_wallet_name && (
          <DetailField label="To Wallet">{tx.to_wallet_name}</DetailField>
        )}
        {tx.fee_amount && (
          <DetailField label="Fee">
            {formatAmount(tx.fee_amount)} {tx.fee_asset_symbol ?? ""}
          </DetailField>
        )}
        {tx.net_value_usd && (
          <DetailField label="USD Value">{formatUsd(tx.net_value_usd)}</DetailField>
        )}
        {tx.label && (
          <DetailField label="Label">{tx.label}</DetailField>
        )}
        {tx.tx_hash && (
          <DetailField label="TX Hash">
            <span className="font-mono text-xs">{tx.tx_hash}</span>
          </DetailField>
        )}
        {tx.description && (
          <DetailField label="Description">{tx.description}</DetailField>
        )}
      </div>
      <div className="mt-3 pt-2" style={{ borderTop: "1px solid var(--border-subtle)" }}>
        <Link
          to={`/transactions/${tx.id}`}
          className="text-xs font-medium hover:underline"
          style={{ color: "var(--accent)" }}
        >
          View full details →
        </Link>
      </div>
    </div>
  );
}

export default function TransactionCard({ tx }: { tx: Transaction }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = getTypeConfig(tx.type);
  const time = new Date(tx.datetime_utc).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
  const truncatedHash = tx.tx_hash
    ? `${tx.tx_hash.slice(0, 6)}…${tx.tx_hash.slice(-4)}`
    : null;

  return (
    <div>
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors"
        style={{ backgroundColor: expanded ? "var(--bg-surface)" : "transparent" }}
        onClick={() => setExpanded(!expanded)}
        onMouseEnter={(e) => {
          if (!expanded) e.currentTarget.style.backgroundColor = "var(--bg-surface-hover)";
        }}
        onMouseLeave={(e) => {
          if (!expanded) e.currentTarget.style.backgroundColor = "transparent";
        }}
      >
        {/* Type badge + label + time */}
        <div className="flex items-center gap-2.5 w-28 flex-shrink-0">
          <TypeBadge type={tx.type} />
          <div>
            <div className="text-sm font-medium flex items-center gap-1.5" style={{ color: cfg.color }}>
              {cfg.label}
              {tx.has_tax_error && (
                <span
                  className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: "var(--danger)" }}
                  title={tx.tax_error || "Tax error"}
                />
              )}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>{time}</div>
          </div>
        </div>

        {/* Flow visualization */}
        <FlowVisualization tx={tx} />

        {/* Right side: USD value + hash + View */}
        <div className="flex items-center gap-3 flex-shrink-0 text-right">
          <div>
            {tx.net_value_usd && (
              <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                {formatUsd(tx.net_value_usd)}
              </div>
            )}
            {truncatedHash && (
              <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                {truncatedHash}
              </div>
            )}
          </div>
          <Link
            to={`/transactions/${tx.id}`}
            className="text-xs hover:underline flex-shrink-0"
            style={{ color: "var(--accent)" }}
            onClick={(e) => e.stopPropagation()}
          >
            View
          </Link>
        </div>
      </div>

      {expanded && <ExpandedDetail tx={tx} />}
    </div>
  );
}
