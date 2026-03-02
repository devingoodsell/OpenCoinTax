import type { HoldingItem, PortfolioStatsResponse } from "../../api/client";
import { formatNumber as fmt } from "../../utils/format";

export { fmt };

const ALLOCATION_COLORS = [
  "#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#ec4899", "#14b8a6", "#f97316", "#a855f7",
  "#64748b", "#84cc16",
];

export function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  const v = parseFloat(value);
  const displayColor = color ?? (v > 0 ? "var(--success)" : v < 0 ? "var(--danger)" : "var(--text-secondary)");
  return (
    <div className="glass-card p-4">
      <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>{label}</div>
      <div className="text-lg font-semibold" style={{ color: displayColor }}>${fmt(value)}</div>
    </div>
  );
}

export function AllocationBar({ holdings }: { holdings: HoldingItem[] }) {
  const withValue = holdings.filter((h) => h.allocation_pct !== null && parseFloat(h.allocation_pct!) > 0);
  if (withValue.length === 0) return null;

  return (
    <div className="glass-card p-4">
      <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Asset Allocation</h2>
      <div className="flex rounded-md overflow-hidden h-7">
        {withValue.map((h, i) => (
          <div
            key={h.asset_symbol}
            className="flex items-center justify-center text-xs font-medium"
            style={{
              width: `${h.allocation_pct}%`,
              backgroundColor: ALLOCATION_COLORS[i % ALLOCATION_COLORS.length],
              color: "#fff",
              minWidth: parseFloat(h.allocation_pct!) > 3 ? undefined : 0,
            }}
            title={`${h.asset_symbol}: ${h.allocation_pct}%`}
          >
            {parseFloat(h.allocation_pct!) > 5 ? h.asset_symbol : ""}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-3 mt-2">
        {withValue.map((h, i) => (
          <div key={h.asset_symbol} className="flex items-center gap-1 text-xs">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: ALLOCATION_COLORS[i % ALLOCATION_COLORS.length] }} />
            <span style={{ color: "var(--text-secondary)" }}>{h.asset_symbol} {h.allocation_pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function StatCards({ stats }: { stats: PortfolioStatsResponse }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
      <StatCard label="In" value={stats.total_in} color="var(--success)" />
      <StatCard label="Out" value={stats.total_out} color="var(--danger)" />
      <StatCard label="Income" value={stats.total_income} color="var(--accent)" />
      <StatCard label="Expenses" value={stats.total_expenses} color="var(--warning)" />
      <StatCard label="Trading Fees" value={stats.total_fees} color="var(--text-secondary)" />
      <StatCard label="Realized Gains" value={stats.realized_gains} />
    </div>
  );
}
