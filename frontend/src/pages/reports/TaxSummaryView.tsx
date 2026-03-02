import { fmt } from "./Form8949View";

function SummarySection({
  title,
  rows,
}: {
  title: string;
  rows: [string, string, boolean?][];
}) {
  return (
    <div className="glass-card p-5 mb-4">
      <h3 className="font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
        {title}
      </h3>
      {rows.map(([label, val, isTotal]) => {
        const num = parseFloat(val);
        const color = isTotal
          ? num >= 0
            ? "var(--success)"
            : "var(--danger)"
          : "var(--text-primary)";
        return (
          <div
            key={label}
            className="flex justify-between py-2 text-sm"
            style={{
              borderBottom: "1px solid var(--border-subtle)",
              fontWeight: isTotal ? 600 : 400,
            }}
          >
            <span style={{ color: "var(--text-secondary)" }}>{label}</span>
            <span style={{ color }}>${fmt(val)}</span>
          </div>
        );
      })}
    </div>
  );
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function SummaryView({ data }: { data: any }) {
  const capitalGains: [string, string, boolean?][] = [
    ["Total Proceeds", data.total_proceeds],
    ["Total Cost Basis", data.total_cost_basis],
    ["Short-Term Gains", data.short_term_gains],
    ["Short-Term Losses", data.short_term_losses],
    ["Long-Term Gains", data.long_term_gains],
    ["Long-Term Losses", data.long_term_losses],
    ["Net Gain/Loss", data.net_gain_loss, true],
  ];

  const income: [string, string, boolean?][] = [
    ["Staking Rewards", data.staking_income],
    ["Airdrops", data.airdrop_income],
    ["Forks", data.fork_income],
    ["Mining", data.mining_income],
    ["Interest", data.interest_income],
    ["Other Income", data.other_income],
    ["Total Income", data.total_income, true],
  ];

  const expenses: [string, string, boolean?][] = [
    ["Cost / Gifts / Lost", data.total_cost_expenses],
    ["Transfer Fees", data.transfer_fees],
    ["Total Fees", data.total_fees_usd, true],
  ];

  const balances = data.eoy_balances || [];

  return (
    <div className="max-w-2xl">
      <SummarySection title="Capital Gains Summary" rows={capitalGains} />
      <SummarySection title="Income Summary" rows={income} />
      <SummarySection title="Expenses" rows={expenses} />

      {balances.length > 0 && (
        <div className="glass-card p-5 mb-4">
          <h3 className="font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
            End of Year Balances
          </h3>
          <table className="w-full text-sm">
            <thead>
              <tr
                className="text-left"
                style={{
                  borderBottom: "1px solid var(--border-default)",
                  color: "var(--text-secondary)",
                }}
              >
                <th className="px-3 py-2">Asset</th>
                <th className="px-3 py-2 text-right">Quantity</th>
                <th className="px-3 py-2 text-right">Cost Basis</th>
                <th className="px-3 py-2 text-right">Market Value (12/31)</th>
              </tr>
            </thead>
            <tbody>
              {balances.map((b: any) => (
                <tr
                  key={b.asset_id}
                  style={{
                    borderBottom: "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                  }}
                >
                  <td className="px-3 py-2">
                    {b.name ? `${b.name} - ${b.symbol}` : b.symbol}
                  </td>
                  <td className="px-3 py-2 text-right">{b.quantity}</td>
                  <td className="px-3 py-2 text-right">${fmt(b.cost_basis_usd)}</td>
                  <td className="px-3 py-2 text-right">
                    {b.market_value_usd ? `$${fmt(b.market_value_usd)}` : "\u2014"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function AuditView({
  checks,
  allPassed,
  comparisons,
  onRunValidation,
  onRunComparison,
}: {
  checks: { check_name: string; status: string; details: string }[] | null;
  allPassed: boolean | null;
  comparisons: { method: string; total_gains: string; total_losses: string; net_gain_loss: string; short_term_net: string; long_term_net: string }[] | null;
  onRunValidation: () => void;
  onRunComparison: () => void;
}) {
  return (
    <div>
      <div className="flex gap-3 mb-6">
        <button
          onClick={onRunValidation}
          className="px-4 py-2 rounded text-sm transition-colors cursor-pointer"
          style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
        >
          Run Invariant Checks
        </button>
        <button
          onClick={onRunComparison}
          className="px-4 py-2 rounded text-sm transition-colors"
          style={{ border: "1px solid var(--border-default)", color: "var(--text-secondary)" }}
        >
          Compare Methods
        </button>
      </div>

      {/* Invariant check results */}
      {checks && (
        <div className="glass-card p-5 mb-6">
          <h2 className="font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
            Invariant Checks:{" "}
            <span style={{ color: allPassed ? "var(--success)" : "var(--danger)" }}>
              {allPassed ? "All Passed" : "Issues Found"}
            </span>
          </h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left" style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
                <th className="px-3 py-2">Check</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Details</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((c) => (
                <tr key={c.check_name} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td className="px-3 py-2" style={{ color: "var(--text-primary)" }}>{c.check_name}</td>
                  <td className="px-3 py-2" style={{ color: c.status === "pass" ? "var(--success)" : "var(--danger)" }}>
                    {c.status}
                  </td>
                  <td className="px-3 py-2" style={{ color: "var(--text-muted)" }}>{c.details}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Method comparison */}
      {comparisons && (
        <div className="glass-card p-5">
          <h2 className="font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Method Comparison</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left" style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
                <th className="px-3 py-2">Method</th>
                <th className="px-3 py-2 text-right">Gains</th>
                <th className="px-3 py-2 text-right">Losses</th>
                <th className="px-3 py-2 text-right">Net</th>
                <th className="px-3 py-2 text-right">ST Net</th>
                <th className="px-3 py-2 text-right">LT Net</th>
              </tr>
            </thead>
            <tbody>
              {comparisons.map((c) => {
                const net = parseFloat(c.net_gain_loss);
                return (
                  <tr key={c.method} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td className="px-3 py-2 font-medium uppercase" style={{ color: "var(--text-primary)" }}>{c.method}</td>
                    <td className="px-3 py-2 text-right" style={{ color: "var(--success)" }}>${c.total_gains}</td>
                    <td className="px-3 py-2 text-right" style={{ color: "var(--danger)" }}>${c.total_losses}</td>
                    <td className="px-3 py-2 text-right font-semibold" style={{ color: net >= 0 ? "var(--success)" : "var(--danger)" }}>
                      ${c.net_gain_loss}
                    </td>
                    <td className="px-3 py-2 text-right" style={{ color: "var(--text-primary)" }}>${c.short_term_net}</td>
                    <td className="px-3 py-2 text-right" style={{ color: "var(--text-primary)" }}>${c.long_term_net}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!checks && !comparisons && (
        <p className="text-sm py-8 text-center" style={{ color: "var(--text-muted)" }}>
          Run invariant checks or compare cost basis methods to audit your tax data.
        </p>
      )}
    </div>
  );
}
