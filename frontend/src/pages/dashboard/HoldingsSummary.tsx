import React, { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import type { HoldingItem } from "../../api/client";
import { fmt } from "./RecentActivity";

type SortKey = "asset" | "balance" | "cost" | "market" | "roi";
type SortDir = "asc" | "desc";

interface Props {
  holdings: HoldingItem[];
  onHide?: (assetId: number) => void;
}

export default function HoldingsSummary({ holdings, onHide }: Props) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("market");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expandedAssets, setExpandedAssets] = useState<Set<number>>(new Set());
  const [showZeroBalance, setShowZeroBalance] = useState(false);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  function toggleExpand(assetId: number) {
    setExpandedAssets((prev) => {
      const next = new Set(prev);
      if (next.has(assetId)) next.delete(assetId);
      else next.add(assetId);
      return next;
    });
  }

  const zeroCount = useMemo(
    () => holdings.filter((h) => !h.market_value_usd || h.market_value_usd === "0.00").length,
    [holdings]
  );

  const filtered = useMemo(() => {
    let result = holdings;
    if (!showZeroBalance) {
      result = result.filter((h) => h.market_value_usd !== null && h.market_value_usd !== "0.00");
    }
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (h) => h.asset_symbol.toLowerCase().includes(q) || (h.asset_name || "").toLowerCase().includes(q)
      );
    }
    const mult = sortDir === "asc" ? 1 : -1;
    result = [...result].sort((a, b) => {
      switch (sortKey) {
        case "asset": return mult * a.asset_symbol.localeCompare(b.asset_symbol);
        case "balance": return mult * (parseFloat(a.total_quantity) - parseFloat(b.total_quantity));
        case "cost": return mult * (parseFloat(a.total_cost_basis_usd) - parseFloat(b.total_cost_basis_usd));
        case "market": return mult * ((parseFloat(a.market_value_usd || "0") || 0) - (parseFloat(b.market_value_usd || "0") || 0));
        case "roi": return mult * ((parseFloat(a.roi_pct || "0") || 0) - (parseFloat(b.roi_pct || "0") || 0));
        default: return 0;
      }
    });
    return result;
  }, [holdings, search, sortKey, sortDir, showZeroBalance]);

  const arrow = (key: SortKey) => sortKey === key ? (sortDir === "asc" ? " \u25B2" : " \u25BC") : "";
  const colCount = onHide ? 6 : 5;

  return (
    <div className="glass-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Holdings</h2>
        <div className="flex items-center gap-2">
          {zeroCount > 0 && (
            <button
              onClick={() => setShowZeroBalance(!showZeroBalance)}
              className="text-xs px-2 py-1 rounded transition-colors"
              style={{
                backgroundColor: showZeroBalance ? "var(--accent)" : "var(--bg-surface)",
                color: showZeroBalance ? "#fff" : "var(--text-muted)",
                border: `1px solid ${showZeroBalance ? "var(--accent)" : "var(--border-default)"}`,
              }}
            >
              {showZeroBalance ? "Hide" : "Show"} {zeroCount} zero-balance asset{zeroCount !== 1 ? "s" : ""}
            </button>
          )}
          <input
            type="text"
            placeholder="Search assets..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded px-3 py-1 text-sm w-48"
            style={{ backgroundColor: "var(--bg-surface)", color: "var(--text-primary)", border: "1px solid var(--border-default)" }}
          />
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
              <th className="text-left pb-2 cursor-pointer select-none" onClick={() => toggleSort("asset")}>Asset{arrow("asset")}</th>
              <th className="text-right pb-2 cursor-pointer select-none" onClick={() => toggleSort("balance")}>Balance{arrow("balance")}</th>
              <th className="text-right pb-2 cursor-pointer select-none" onClick={() => toggleSort("cost")}>Cost (USD){arrow("cost")}</th>
              <th className="text-right pb-2 cursor-pointer select-none" onClick={() => toggleSort("market")}>Market Value{arrow("market")}</th>
              <th className="text-right pb-2 cursor-pointer select-none" onClick={() => toggleSort("roi")}>ROI %{arrow("roi")}</th>
              {onHide && <th className="text-right pb-2 w-16"></th>}
            </tr>
          </thead>
          <tbody>
            {filtered.map((h) => {
              const roi = h.roi_pct ? parseFloat(h.roi_pct) : null;
              const qty = parseFloat(h.total_quantity);
              const cost = parseFloat(h.total_cost_basis_usd);
              const costPerUnit = qty > 0 ? cost / qty : 0;
              const mv = h.market_value_usd ? parseFloat(h.market_value_usd) : null;
              const pricePerUnit = h.current_price_usd ? parseFloat(h.current_price_usd) : null;
              const isExpanded = expandedAssets.has(h.asset_id);
              const hasBreakdown = h.wallet_breakdown && h.wallet_breakdown.length > 0;
              return (
                <React.Fragment key={h.asset_id}>
                  <tr
                    style={{ borderBottom: isExpanded ? "none" : "1px solid var(--border-subtle)", cursor: hasBreakdown ? "pointer" : undefined }}
                    onClick={hasBreakdown ? () => toggleExpand(h.asset_id) : undefined}
                  >
                    <td className="py-2" style={{ color: "var(--text-primary)" }}>
                      {hasBreakdown && <span className="inline-block w-4 text-center mr-1" style={{ color: "var(--text-muted)", fontSize: "10px" }}>{isExpanded ? "\u25BC" : "\u25B6"}</span>}
                      {!hasBreakdown && <span className="inline-block w-4 mr-1" />}
                      <span className="font-medium">{h.asset_symbol}</span>
                      {h.asset_name && <span className="ml-2 text-xs" style={{ color: "var(--text-muted)" }}>{h.asset_name}</span>}
                    </td>
                    <td className="py-2 text-right" style={{ color: "var(--text-primary)" }}>{fmt(h.total_quantity, 8).replace(/\.?0+$/, "")}</td>
                    <td className="py-2 text-right" style={{ color: "var(--text-primary)" }}>
                      <div>${fmt(cost)}</div>
                      <div className="text-xs" style={{ color: "var(--text-muted)" }}>@${fmt(costPerUnit)}</div>
                    </td>
                    <td className="py-2 text-right" style={{ color: "var(--text-primary)" }}>
                      {mv !== null ? (
                        <>
                          <div>${fmt(mv)}</div>
                          {pricePerUnit !== null && <div className="text-xs" style={{ color: "var(--text-muted)" }}>@${fmt(pricePerUnit)}</div>}
                        </>
                      ) : <span style={{ color: "var(--text-muted)" }}>—</span>}
                    </td>
                    <td className="py-2 text-right font-medium" style={{ color: roi === null ? "var(--text-muted)" : roi >= 0 ? "var(--success)" : "var(--danger)" }}>
                      {roi !== null ? `${roi >= 0 ? "+" : ""}${fmt(roi)}%` : "—"}
                    </td>
                    {onHide && (
                      <td className="py-2 text-right">
                        <button onClick={(e) => { e.stopPropagation(); onHide(h.asset_id); }} className="text-xs px-2 py-0.5 rounded transition-colors" style={{ backgroundColor: "var(--bg-surface-hover)", color: "var(--text-muted)" }} title="Hide this asset">Hide</button>
                      </td>
                    )}
                  </tr>
                  {isExpanded && h.wallet_breakdown?.map((wb) => {
                    const wbQty = parseFloat(wb.quantity);
                    const wbVal = wb.value_usd ? parseFloat(wb.value_usd) : null;
                    const allocationPct = qty > 0 ? ((wbQty / qty) * 100).toFixed(1) : "0";
                    return (
                      <tr key={wb.wallet_id} style={{ borderBottom: "1px solid var(--border-subtle)", backgroundColor: "rgba(255,255,255,0.02)" }}>
                        <td className="py-1.5 pl-9 text-xs">
                          <Link to={`/wallets/${wb.wallet_id}`} className="hover:underline" style={{ color: "var(--accent)" }} onClick={(e) => e.stopPropagation()}>{wb.wallet_name}</Link>
                        </td>
                        <td className="py-1.5 text-right text-xs" style={{ color: "var(--text-secondary)" }}>{fmt(wb.quantity, 8).replace(/\.?0+$/, "")}</td>
                        <td className="py-1.5 text-right text-xs" style={{ color: "var(--text-muted)" }}></td>
                        <td className="py-1.5 text-right text-xs" style={{ color: "var(--text-secondary)" }}>{wbVal !== null ? `$${fmt(wbVal)}` : "—"}</td>
                        <td className="py-1.5 text-right text-xs" style={{ color: "var(--text-muted)" }}>{allocationPct}%</td>
                        {onHide && <td />}
                      </tr>
                    );
                  })}
                </React.Fragment>
              );
            })}
            {filtered.length === 0 && (
              <tr><td colSpan={colCount} className="py-6 text-center" style={{ color: "var(--text-muted)" }}>No holdings found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
