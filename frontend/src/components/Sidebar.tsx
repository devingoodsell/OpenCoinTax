import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Dashboard" },
  { to: "/transactions", label: "Transactions" },
  { to: "/wallets", label: "Wallets" },
  { to: "/import", label: "Import" },
  { to: "/reports", label: "Reports" },
  { to: "/settings", label: "Settings" },
];

export default function Sidebar() {
  return (
    <aside
      className="w-56 shrink-0 flex flex-col min-h-screen"
      style={{
        backgroundColor: "var(--bg-base)",
        borderRight: "1px solid var(--border-subtle)",
        color: "var(--text-primary)",
      }}
    >
      <div
        className="p-4 text-lg font-bold"
        style={{ borderBottom: "1px solid var(--border-subtle)" }}
      >
        Crypto Tax
      </div>

      <nav className="flex-1 py-2">
        {links.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `block px-4 py-2 text-sm transition-colors duration-150 ${
                isActive
                  ? "font-semibold"
                  : ""
              }`
            }
            style={({ isActive }) => ({
              color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
              backgroundColor: isActive ? "var(--bg-surface-hover)" : "transparent",
              borderLeft: isActive ? "3px solid var(--accent)" : "3px solid transparent",
            })}
          >
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
