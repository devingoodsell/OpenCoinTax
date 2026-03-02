import { Link } from "react-router-dom";
import type { WalletDetail } from "../../api/client";

const badgeColors: Record<string, string> = {
  gray: "rgba(161, 161, 170, 0.15)",
  green: "rgba(34, 197, 94, 0.15)",
  red: "rgba(239, 68, 68, 0.15)",
  purple: "rgba(168, 85, 247, 0.15)",
  blue: "rgba(59, 130, 246, 0.15)",
  orange: "rgba(249, 115, 22, 0.15)",
  teal: "rgba(20, 184, 166, 0.15)",
};

const badgeTextColors: Record<string, string> = {
  gray: "#a1a1aa",
  green: "#4ade80",
  red: "#f87171",
  purple: "#c084fc",
  blue: "#60a5fa",
  orange: "#fb923c",
  teal: "#2dd4bf",
};

export function TxSummaryBadges({
  summary,
}: {
  summary: WalletDetail["transaction_summary"];
}) {
  const badges = [
    { label: "Total", value: summary.total, color: "gray" },
    { label: "Buys", value: summary.buys, color: "green" },
    { label: "Sells", value: summary.sells, color: "red" },
    { label: "Trades", value: summary.trades, color: "purple" },
    { label: "Deposits", value: summary.deposits, color: "blue" },
    { label: "Withdrawals", value: summary.withdrawals, color: "orange" },
    { label: "Transfers", value: summary.transfers, color: "teal" },
  ];

  return (
    <div className="flex flex-wrap gap-2">
      {badges.map(
        (b) =>
          b.value > 0 && (
            <span
              key={b.label}
              className="text-xs px-2 py-0.5 rounded"
              style={{
                background: badgeColors[b.color] || badgeColors.gray,
                color: badgeTextColors[b.color] || badgeTextColors.gray,
              }}
            >
              {b.value} {b.label}
            </span>
          )
      )}
    </div>
  );
}

export default function WalletTransactionSummary({
  summary,
  walletId,
}: {
  summary: WalletDetail["transaction_summary"];
  walletId: number;
}) {
  return (
    <div className="mb-4 flex items-center justify-between">
      <TxSummaryBadges summary={summary} />
      {summary.total > 0 && (
        <Link
          to={`/transactions?wallet_id=${walletId}`}
          className="text-xs font-medium hover:underline flex-shrink-0"
          style={{ color: "var(--accent)" }}
        >
          View all transactions →
        </Link>
      )}
    </div>
  );
}
