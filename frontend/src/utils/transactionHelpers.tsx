const TX_TYPE_CONFIG: Record<string, { icon: string; color: string; bg: string; label: string }> = {
  buy:            { icon: "\u2193", color: "#16a34a", bg: "rgba(22,163,74,0.12)",  label: "Buy" },
  sell:           { icon: "\u2191", color: "#dc2626", bg: "rgba(220,38,38,0.12)",  label: "Sell" },
  trade:          { icon: "\u21C4", color: "#9333ea", bg: "rgba(147,51,234,0.12)", label: "Trade" },
  transfer:       { icon: "\u2192", color: "#0d9488", bg: "rgba(13,148,136,0.12)", label: "Transfer" },
  deposit:        { icon: "\u2193", color: "#2563eb", bg: "rgba(37,99,235,0.12)",  label: "Deposit" },
  withdrawal:     { icon: "\u2191", color: "#ea580c", bg: "rgba(234,88,12,0.12)",  label: "Withdrawal" },
  staking_reward: { icon: "\u2605", color: "#d97706", bg: "rgba(217,119,6,0.12)",  label: "Reward" },
  airdrop:        { icon: "\u2193", color: "#7c3aed", bg: "rgba(124,58,237,0.12)", label: "Airdrop" },
  mining:         { icon: "\u26CF", color: "#d97706", bg: "rgba(217,119,6,0.12)",  label: "Mining" },
  interest:       { icon: "%", color: "#059669", bg: "rgba(5,150,105,0.12)",   label: "Interest" },
  gift_received:  { icon: "\u2193", color: "#7c3aed", bg: "rgba(124,58,237,0.12)", label: "Gift" },
  gift_sent:      { icon: "\u2191", color: "#ea580c", bg: "rgba(234,88,12,0.12)",  label: "Gift Sent" },
  cost:           { icon: "$", color: "#d97706", bg: "rgba(217,119,6,0.12)",  label: "Cost" },
  fork:           { icon: "\u2193", color: "#2563eb", bg: "rgba(37,99,235,0.12)",  label: "Fork" },
};

const DEFAULT_TYPE_CONFIG = { icon: "\u2022", color: "var(--text-secondary)", bg: "var(--bg-surface)", label: "" };

export function getTypeConfig(type: string) {
  return TX_TYPE_CONFIG[type] || { ...DEFAULT_TYPE_CONFIG, label: type };
}

export { formatCrypto as formatAmount, formatCurrency as formatUsd } from "./format";

export function TypeBadge({ type }: { type: string }) {
  const cfg = getTypeConfig(type);
  return (
    <div
      className="flex items-center justify-center rounded-lg flex-shrink-0"
      style={{
        width: 32,
        height: 32,
        backgroundColor: cfg.bg,
        color: cfg.color,
        fontSize: 16,
        fontWeight: 600,
      }}
    >
      {cfg.icon}
    </div>
  );
}
