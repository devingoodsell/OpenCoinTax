import { formatAmount, formatUsd } from "../../utils/transactionHelpers";
import { computeTotals, type TxDetail } from "./TransactionInfo";

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-3" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
      <span className="text-sm" style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{value}</span>
    </div>
  );
}

export function LedgerTab({ tx }: { tx: TxDetail }) {
  if (!tx.lot_assignments || tx.lot_assignments.length === 0) {
    return <div className="p-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>No lot assignments for this transaction type</div>;
  }

  return (
    <div className="p-5 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
            <th className="pb-2 text-left font-medium">Amount</th>
            <th className="pb-2 text-right font-medium">Cost Basis</th>
            <th className="pb-2 text-right font-medium">Proceeds</th>
            <th className="pb-2 text-right font-medium">Gain/Loss</th>
            <th className="pb-2 text-left font-medium pl-4">Period</th>
          </tr>
        </thead>
        <tbody>
          {tx.lot_assignments.map((a) => {
            const gl = parseFloat(a.gain_loss_usd);
            return (
              <tr key={a.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                <td className="py-2.5" style={{ color: "var(--text-primary)" }}>{formatAmount(a.amount)} {tx.from_asset_symbol}</td>
                <td className="py-2.5 text-right" style={{ color: "var(--text-primary)" }}>{formatUsd(a.cost_basis_usd)}</td>
                <td className="py-2.5 text-right" style={{ color: "var(--text-primary)" }}>{formatUsd(a.proceeds_usd)}</td>
                <td className="py-2.5 text-right font-medium" style={{ color: gl >= 0 ? "var(--success)" : "var(--danger)" }}>{gl >= 0 ? "+" : ""}{formatUsd(a.gain_loss_usd)}</td>
                <td className="py-2.5 pl-4">
                  <span className="px-2 py-0.5 rounded-full text-xs font-medium" style={{
                    backgroundColor: a.holding_period === "long_term" ? "rgba(37,99,235,0.1)" : "rgba(217,119,6,0.1)",
                    color: a.holding_period === "long_term" ? "#2563eb" : "#d97706",
                  }}>{a.holding_period === "long_term" ? "Long-term" : "Short-term"}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function CostAnalysisTab({ tx }: { tx: TxDetail }) {
  if (!tx.lot_assignments || tx.lot_assignments.length === 0) {
    return <div className="p-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>No cost analysis available for this transaction type</div>;
  }

  const { totalCost, totalProceeds, totalGain, shortTermGain, longTermGain } = computeTotals(tx.lot_assignments);
  const hasShortTerm = tx.lot_assignments.some((a) => a.holding_period !== "long_term");
  const hasLongTerm = tx.lot_assignments.some((a) => a.holding_period === "long_term");

  return (
    <div className="p-5 space-y-4">
      <div className="rounded-lg p-4 space-y-0" style={{ backgroundColor: "var(--bg-surface)", border: "1px solid var(--border-default)" }}>
        <SummaryRow label="Total Cost Basis" value={formatUsd(totalCost.toFixed(2))} />
        <SummaryRow label="Total Proceeds" value={formatUsd(totalProceeds.toFixed(2))} />
        <div className="flex items-center justify-between py-3">
          <span className="text-sm" style={{ color: "var(--text-secondary)" }}>Total Realized Gain/Loss</span>
          <span className="text-sm font-semibold" style={{ color: totalGain >= 0 ? "var(--success)" : "var(--danger)" }}>{totalGain >= 0 ? "+" : ""}{formatUsd(totalGain.toFixed(2))}</span>
        </div>
      </div>
      {(hasShortTerm || hasLongTerm) && (
        <div className="rounded-lg p-4" style={{ backgroundColor: "var(--bg-surface)", border: "1px solid var(--border-default)" }}>
          <div className="text-xs font-medium mb-3" style={{ color: "var(--text-muted)" }}>Holding Period Breakdown</div>
          {hasShortTerm && (
            <div className="flex items-center justify-between py-2">
              <span className="px-2 py-0.5 rounded-full text-xs font-medium" style={{ backgroundColor: "rgba(217,119,6,0.1)", color: "#d97706" }}>Short-term</span>
              <span className="text-sm font-medium" style={{ color: shortTermGain >= 0 ? "var(--success)" : "var(--danger)" }}>{shortTermGain >= 0 ? "+" : ""}{formatUsd(shortTermGain.toFixed(2))}</span>
            </div>
          )}
          {hasLongTerm && (
            <div className="flex items-center justify-between py-2">
              <span className="px-2 py-0.5 rounded-full text-xs font-medium" style={{ backgroundColor: "rgba(37,99,235,0.1)", color: "#2563eb" }}>Long-term</span>
              <span className="text-sm font-medium" style={{ color: longTermGain >= 0 ? "var(--success)" : "var(--danger)" }}>{longTermGain >= 0 ? "+" : ""}{formatUsd(longTermGain.toFixed(2))}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
