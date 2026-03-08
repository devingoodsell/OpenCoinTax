import { Link, NavLink } from "react-router-dom";

const links = [
  { to: "/transactions", label: "Transactions" },
  { to: "/wallets", label: "Wallets" },
  { to: "/import", label: "Import" },
  { to: "/reports", label: "Reports" },
  { to: "/settings", label: "Settings" },
];

export default function TopNav() {
  return (
    <nav
      className="w-full flex items-center px-6 shrink-0"
      style={{
        height: 56,
        backgroundColor: "var(--bg-base)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      {/* App logo + title — links to dashboard */}
      <Link to="/" className="flex items-center gap-2.5 mr-8 whitespace-nowrap no-underline">
        <img src="/favicon.svg" alt="OpenCoinTax" width={28} height={28} className="rounded" />
        <span className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>
          Open<span style={{ color: "var(--accent)" }}>Coin</span>Tax
        </span>
      </Link>

      {/* Navigation links */}
      <div className="flex items-center gap-1 flex-1 overflow-x-auto scrollbar-none">
        {links.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className="px-3 py-1 text-sm whitespace-nowrap rounded transition-colors duration-150"
            style={({ isActive }) => ({
              color: isActive ? "var(--accent)" : "var(--text-secondary)",
              fontWeight: isActive ? 600 : 400,
              borderBottom: isActive ? "2px solid var(--accent)" : "2px solid transparent",
              paddingBottom: isActive ? 14 : 16,
              marginBottom: -1,
            })}
          >
            {label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
