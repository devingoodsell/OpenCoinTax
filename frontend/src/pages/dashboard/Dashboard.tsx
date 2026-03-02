import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchDailyValues,
  fetchPortfolioHoldings,
  fetchPortfolioStats,
  fetchTransactionErrorCount,
  refreshCurrentPrices,
  backfillPrices,
  hideAsset,
  unhideAsset,
  fetchHiddenAssets,
  type DailyValuesResponse,
  type HoldingsResponse,
  type PortfolioStatsResponse,
} from "../../api/client";
import LoadingSpinner from "../../components/LoadingSpinner";
import ErrorBanner from "../../components/ErrorBanner";
import PortfolioChart from "./PortfolioChart";
import HoldingsSummary from "./HoldingsSummary";
import { AllocationBar, StatCards, fmt } from "./RecentActivity";

type Preset = "YTD" | "1M" | "3M" | "6M" | "1Y" | "ALL";
const PRESETS: Preset[] = ["YTD", "1M", "3M", "6M", "1Y", "ALL"];

function dateStr(d: Date): string {
  return d.toISOString().split("T")[0];
}

function presetRange(preset: Preset): [string, string] {
  const end = new Date();
  const start = new Date();
  switch (preset) {
    case "YTD": start.setMonth(0); start.setDate(1); break;
    case "1M": start.setMonth(start.getMonth() - 1); break;
    case "3M": start.setMonth(start.getMonth() - 3); break;
    case "6M": start.setMonth(start.getMonth() - 6); break;
    case "1Y": start.setFullYear(start.getFullYear() - 1); break;
    case "ALL": start.setFullYear(start.getFullYear() - 10); break;
  }
  return [dateStr(start), dateStr(end)];
}

export default function Dashboard() {
  const [activePreset, setActivePreset] = useState<Preset>("1Y");
  const [startDate, setStartDate] = useState(() => presetRange("1Y")[0]);
  const [endDate, setEndDate] = useState(() => presetRange("1Y")[1]);
  const [dailyData, setDailyData] = useState<DailyValuesResponse | null>(null);
  const [holdings, setHoldings] = useState<HoldingsResponse | null>(null);
  const [stats, setStats] = useState<PortfolioStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [taxErrorCount, setTaxErrorCount] = useState(0);
  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [backfilling, setBackfilling] = useState(false);
  const [hiddenAssets, setHiddenAssets] = useState<{ id: number; symbol: string; name: string | null }[]>([]);
  const [showHidden, setShowHidden] = useState(false);

  function load(sd: string, ed: string) {
    setLoading(true);
    setError("");
    Promise.all([fetchDailyValues(sd, ed), fetchPortfolioHoldings(), fetchPortfolioStats(sd, ed)])
      .then(([dv, h, s]) => { setDailyData(dv.data); setHoldings(h.data); setStats(s.data); })
      .catch((e) => setError(e.response?.data?.detail || "Failed to load portfolio data"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load(startDate, endDate);
    fetchHiddenAssets().then((r) => setHiddenAssets(r.data)).catch(() => {});
    fetchTransactionErrorCount().then((r) => setTaxErrorCount(r.data.error_count)).catch(() => {});
  }, [startDate, endDate]);

  function handleHideAsset(assetId: number) {
    if (!holdings) return;
    const item = holdings.holdings.find((h) => h.asset_id === assetId);
    if (!item) return;
    const remaining = holdings.holdings.filter((h) => h.asset_id !== assetId);
    const newTotal = remaining.reduce((sum, h) => sum + (parseFloat(h.market_value_usd || "0") || 0), 0);
    setHoldings({ holdings: remaining, total_portfolio_value: newTotal.toFixed(2) });
    setHiddenAssets((prev) => [...prev, { id: assetId, symbol: item.asset_symbol, name: item.asset_name }]);
    hideAsset(assetId).catch(() => {
      setHoldings(holdings);
      setHiddenAssets((prev) => prev.filter((a) => a.id !== assetId));
    });
  }

  function handleUnhideAsset(assetId: number) {
    const item = hiddenAssets.find((a) => a.id === assetId);
    if (!item) return;
    setHiddenAssets((prev) => prev.filter((a) => a.id !== assetId));
    unhideAsset(assetId)
      .then(() => { fetchPortfolioHoldings().then((r) => setHoldings(r.data)).catch(() => {}); })
      .catch(() => { setHiddenAssets((prev) => [...prev, item]); });
  }

  async function handleRefreshPrices() {
    setRefreshingPrices(true);
    try { await refreshCurrentPrices(); load(startDate, endDate); } catch {} finally { setRefreshingPrices(false); }
  }

  async function handleBackfill() {
    setBackfilling(true);
    try { await backfillPrices(); load(startDate, endDate); } catch { setError("Failed to backfill prices"); } finally { setBackfilling(false); }
  }

  function selectPreset(p: Preset) { setActivePreset(p); const [s, e] = presetRange(p); setStartDate(s); setEndDate(e); }

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorBanner message={error} onRetry={() => load(startDate, endDate)} />;

  const hasChartData = dailyData && dailyData.data_points.length > 0 && dailyData.data_points.some(dp => parseFloat(dp.total_value_usd) > 0);
  const hasHoldings = holdings && holdings.holdings.length > 0;
  const hasStats = stats && (parseFloat(stats.total_in) > 0 || parseFloat(stats.total_out) > 0 || parseFloat(stats.total_income) > 0 || parseFloat(stats.total_fees) > 0);

  const summary = dailyData?.summary;
  const currentValue = summary ? parseFloat(summary.current_value) : 0;
  const costBasis = summary ? parseFloat(summary.total_cost_basis) : 0;
  const unrealizedGain = summary ? parseFloat(summary.unrealized_gain) : 0;
  const unrealizedPct = summary ? parseFloat(summary.unrealized_gain_pct) : 0;

  const rawChartData = (dailyData?.data_points ?? []).map((dp) => ({ date: dp.date, value: parseFloat(dp.total_value_usd) }));
  const firstNonZero = rawChartData.findIndex((dp) => dp.value > 0);
  const chartData = firstNonZero >= 0 ? rawChartData.slice(Math.max(0, firstNonZero - 1)) : rawChartData;

  return (
    <div>
      {/* Date range picker */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>Portfolio</h1>
        <div className="flex items-center gap-2">
          <button onClick={handleBackfill} disabled={backfilling} className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 cursor-pointer" style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
            title="Fetch daily historical prices from CoinGecko to populate the chart">
            {backfilling ? "Backfilling..." : "Backfill Chart"}
          </button>
          <button onClick={handleRefreshPrices} disabled={refreshingPrices} className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 cursor-pointer" style={{ border: "1px solid var(--success)", color: "var(--success)" }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--success)"; e.currentTarget.style.color = "#fff"; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--success)"; }}>
            {refreshingPrices ? "Refreshing..." : "Refresh Prices"}
          </button>
          {PRESETS.map((p) => (
            <button key={p} onClick={() => selectPreset(p)} className="px-3 py-1 text-sm rounded transition-colors" style={{
              backgroundColor: activePreset === p ? "var(--accent)" : "var(--bg-surface)",
              color: activePreset === p ? "#fff" : "var(--text-secondary)",
              border: activePreset === p ? "1px solid var(--accent)" : "1px solid var(--border-default)",
            }}>{p}</button>
          ))}
          <input type="date" value={startDate} onChange={(e) => { setStartDate(e.target.value); setActivePreset("ALL"); }} className="rounded px-2 py-1 text-sm" style={{ backgroundColor: "var(--bg-surface)", color: "var(--text-primary)", border: "1px solid var(--border-default)" }} />
          <span style={{ color: "var(--text-muted)" }}>–</span>
          <input type="date" value={endDate} onChange={(e) => { setEndDate(e.target.value); setActivePreset("1Y"); }} className="rounded px-2 py-1 text-sm" style={{ backgroundColor: "var(--bg-surface)", color: "var(--text-primary)", border: "1px solid var(--border-default)" }} />
        </div>
      </div>

      {!hasChartData && !hasHoldings && !hasStats && (
        <div className="glass-card p-5 mb-4" style={{ borderLeft: "3px solid var(--accent)" }}>
          <h2 className="font-semibold mb-2" style={{ color: "var(--text-primary)" }}>Getting Started</h2>
          <p className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>Your portfolio dashboard will show data once you have transactions with USD valuations and price history.</p>
          <div className="flex flex-wrap gap-3">
            <a href="/import" className="px-4 py-2 rounded text-sm font-medium transition-colors cursor-pointer" style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}>Import Transactions</a>
            <a href="/import?tab=koinly" className="px-4 py-2 rounded text-sm font-medium transition-colors" style={{ backgroundColor: "var(--bg-surface)", color: "var(--text-primary)", border: "1px solid var(--border-default)" }}>Import from Koinly</a>
          </div>
        </div>
      )}

      {taxErrorCount > 0 && (
        <div className="glass-card p-4 mb-4 flex items-center justify-between" style={{ borderLeft: "4px solid var(--danger)" }}>
          <div>
            <div className="font-semibold text-sm" style={{ color: "var(--danger)" }}>{taxErrorCount} Transaction{taxErrorCount !== 1 ? "s" : ""} with Tax Errors</div>
            <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>These transactions could not be processed by the tax engine and need correction.</div>
          </div>
          <Link to="/transactions?has_errors=true" className="px-3 py-1.5 rounded text-sm font-medium transition-colors cursor-pointer" style={{ border: "1px solid var(--danger)", color: "var(--danger)" }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--danger)"; e.currentTarget.style.color = "#fff"; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--danger)"; }}>View Errors</Link>
        </div>
      )}

      {/* Portfolio value summary */}
      <div className="glass-card p-5 mb-4">
        <div className="flex items-end gap-6 flex-wrap">
          <div>
            <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Total Value</div>
            <div className="text-3xl font-bold" style={{ color: currentValue > 0 ? "var(--success)" : "var(--text-secondary)" }}>${fmt(currentValue)}</div>
          </div>
          <div>
            <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Change</div>
            <div className="text-lg font-semibold" style={{ color: unrealizedPct >= 0 ? "var(--success)" : "var(--danger)" }}>{unrealizedPct >= 0 ? "+" : ""}{fmt(unrealizedPct)}%</div>
          </div>
          <div>
            <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Cost Basis</div>
            <div className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>${fmt(costBasis)}</div>
          </div>
          <div>
            <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Unrealized Gain</div>
            <div className="text-lg font-semibold" style={{ color: unrealizedGain >= 0 ? "var(--success)" : "var(--danger)" }}>{unrealizedGain >= 0 ? "+" : ""}${fmt(unrealizedGain)}</div>
          </div>
        </div>
      </div>

      <PortfolioChart chartData={hasChartData ? chartData : []} />
      {stats && <StatCards stats={stats} />}
      {holdings && <AllocationBar holdings={holdings.holdings} />}
      {hasHoldings && <div className="mt-4"><HoldingsSummary holdings={holdings!.holdings} onHide={handleHideAsset} /></div>}

      {hiddenAssets.length > 0 && (
        <div className="mt-4">
          <button onClick={() => setShowHidden(!showHidden)} className="text-xs px-3 py-1.5 rounded transition-colors" style={{ backgroundColor: "var(--bg-surface)", color: "var(--text-muted)", border: "1px solid var(--border-default)" }}>
            {showHidden ? "Hide" : "Show"} {hiddenAssets.length} hidden asset{hiddenAssets.length !== 1 ? "s" : ""}
          </button>
          {showHidden && (
            <div className="glass-card p-4 mt-2">
              <table className="w-full text-sm">
                <thead><tr style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-secondary)" }}><th className="text-left pb-2">Asset</th><th className="text-right pb-2"></th></tr></thead>
                <tbody>
                  {hiddenAssets.map((a) => (
                    <tr key={a.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      <td className="py-2" style={{ color: "var(--text-primary)" }}>
                        <span className="font-medium">{a.symbol}</span>
                        {a.name && <span className="ml-2 text-xs" style={{ color: "var(--text-muted)" }}>{a.name}</span>}
                      </td>
                      <td className="py-2 text-right">
                        <button onClick={() => handleUnhideAsset(a.id)} className="text-xs px-2 py-0.5 rounded transition-colors" style={{ backgroundColor: "var(--bg-surface-hover)", color: "var(--text-muted)" }}>Unhide</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
