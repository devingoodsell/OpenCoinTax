import { useState } from "react";
import {
  refreshCurrentPrices,
  hideAsset,
  type WalletDetail,
} from "../../api/client";

interface Props {
  wallet: WalletDetail;
  setWallet: React.Dispatch<React.SetStateAction<WalletDetail | null>>;
  setError: (msg: string) => void;
  loadWallet: () => void;
}

export default function WalletHoldings({ wallet, setWallet, setError, loadWallet }: Props) {
  const [refreshingPrices, setRefreshingPrices] = useState(false);

  async function handleRefreshPrices() {
    setRefreshingPrices(true);
    try {
      await refreshCurrentPrices();
      loadWallet();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to refresh prices");
    } finally {
      setRefreshingPrices(false);
    }
  }

  function handleHideAsset(assetId: number) {
    const prev = wallet;
    setWallet({
      ...wallet,
      balances: wallet.balances.filter((b) => b.asset_id !== assetId),
    });
    hideAsset(assetId).catch(() => {
      setWallet(prev);
    });
  }

  if (!wallet.balances || wallet.balances.length === 0) {
    return (
      <div className="text-sm text-center py-8" style={{ color: "var(--text-muted)" }}>
        No holdings found. Sync or import transactions to see balances.
      </div>
    );
  }

  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold" style={{ color: "var(--text-primary)" }}>Holdings</h2>
        <button
          onClick={handleRefreshPrices}
          disabled={refreshingPrices}
          className="text-xs px-3 py-1 text-white rounded disabled:opacity-50 transition-colors"
          style={{ backgroundColor: "var(--accent)" }}
        >
          {refreshingPrices ? "Refreshing..." : "Refresh Prices"}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left" style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
              <th className="pb-2">Asset</th>
              <th className="pb-2 text-right">Quantity</th>
              <th className="pb-2 text-right">Cost Basis</th>
              <th className="pb-2 text-right">Price</th>
              <th className="pb-2 text-right">Market Value</th>
              <th className="pb-2 text-right">ROI</th>
              <th className="pb-2 text-right w-16"></th>
            </tr>
          </thead>
          <tbody>
            {wallet.balances.map((b) => {
              const roi = b.roi_pct ? parseFloat(b.roi_pct) : null;
              return (
                <tr key={b.symbol} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td className="py-2" style={{ color: "var(--text-primary)" }}>{b.symbol}</td>
                  <td className="py-2 text-right" style={{ color: "var(--text-primary)" }}>{b.quantity}</td>
                  <td className="py-2 text-right" style={{ color: "var(--text-primary)" }}>
                    ${Number(b.cost_basis_usd).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </td>
                  <td className="py-2 text-right" style={{ color: "var(--text-primary)" }}>
                    {b.current_price_usd
                      ? `$${Number(b.current_price_usd).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      : <span style={{ color: "var(--text-muted)" }}>--</span>}
                  </td>
                  <td className="py-2 text-right" style={{ color: "var(--text-primary)" }}>
                    {b.market_value_usd
                      ? `$${Number(b.market_value_usd).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      : <span style={{ color: "var(--text-muted)" }}>--</span>}
                  </td>
                  <td
                    className="py-2 text-right font-medium"
                    style={{
                      color: roi === null ? "var(--text-muted)" : roi >= 0 ? "var(--success)" : "var(--danger)",
                    }}
                  >
                    {roi !== null ? `${roi >= 0 ? "+" : ""}${roi.toFixed(2)}%` : "--"}
                  </td>
                  <td className="py-2 text-right">
                    <button
                      onClick={() => handleHideAsset(b.asset_id)}
                      className="text-xs px-2 py-0.5 rounded transition-colors"
                      style={{ backgroundColor: "var(--bg-surface-hover)", color: "var(--text-muted)" }}
                      title="Hide this asset"
                    >
                      Hide
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
