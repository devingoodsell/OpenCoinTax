import { useState } from "react";
import { Link } from "react-router-dom";
import {
  syncExchange,
  createExchangeConnection,
  deleteExchangeConnection,
  type WalletDetail,
  type SyncResult,
} from "../../api/client";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

interface Props {
  wallet: WalletDetail;
  loadWallet: () => void;
  setError: (msg: string) => void;
}

export default function WalletImportSync({ wallet, loadWallet, setError }: Props) {
  const [exchangeSyncing, setExchangeSyncing] = useState(false);
  const [exchangeSyncResult, setExchangeSyncResult] = useState<SyncResult | null>(null);
  const [exchangeSyncError, setExchangeSyncError] = useState("");
  const [showConnForm, setShowConnForm] = useState(false);
  const [connType, setConnType] = useState("coinbase");
  const [connApiKey, setConnApiKey] = useState("");
  const [connApiSecret, setConnApiSecret] = useState("");

  async function handleExchangeSync() {
    setExchangeSyncing(true);
    setExchangeSyncResult(null);
    setExchangeSyncError("");
    try {
      const resp = await syncExchange(wallet.id);
      setExchangeSyncResult(resp.data);
      loadWallet();
    } catch (err: any) {
      setExchangeSyncError(err?.response?.data?.detail || "Sync failed");
    } finally {
      setExchangeSyncing(false);
    }
  }

  async function handleSaveConnection(e: React.FormEvent) {
    e.preventDefault();
    try {
      await createExchangeConnection(wallet.id, {
        exchange_type: connType,
        api_key: connApiKey,
        api_secret: connApiSecret,
      });
      setShowConnForm(false);
      setConnApiKey("");
      setConnApiSecret("");
      loadWallet();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to save connection");
    }
  }

  async function handleDeleteConnection() {
    if (!confirm("Remove API connection?")) return;
    try {
      await deleteExchangeConnection(wallet.id);
      loadWallet();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to remove connection");
    }
  }

  return (
    <div className="space-y-4">
      {/* CSV Import link */}
      <div className="glass-card p-4">
        <h3 className="font-semibold text-sm mb-1" style={{ color: "var(--text-primary)" }}>CSV Import</h3>
        <p className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>Upload a CSV export from your exchange.</p>
        <Link to={`/import?wallet=${wallet.id}`} className="text-sm hover:underline" style={{ color: "var(--accent)" }}>
          Go to CSV Import &rarr;
        </Link>
      </div>

      {/* Exchange API Sync */}
      <div className="glass-card p-4">
        <h3 className="font-semibold text-sm mb-1" style={{ color: "var(--text-primary)" }}>API Sync</h3>
        {wallet.has_exchange_connection ? (
          <div>
            <div className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>
              API connection configured.{" "}
              {wallet.exchange_last_synced_at ? `Last synced ${timeAgo(wallet.exchange_last_synced_at)}` : "Never synced."}
            </div>
            <div className="flex gap-2">
              <button onClick={handleExchangeSync} disabled={exchangeSyncing} className="px-3 py-1.5 text-white rounded text-sm disabled:opacity-50 transition-colors" style={{ backgroundColor: "var(--accent)" }}>
                {exchangeSyncing ? "Syncing..." : "Sync Now"}
              </button>
              <button onClick={() => setShowConnForm(true)} className="px-3 py-1.5 rounded text-sm transition-colors" style={{ backgroundColor: "var(--bg-surface-hover)", color: "var(--text-secondary)" }}>
                Update Keys
              </button>
              <button onClick={handleDeleteConnection} className="px-3 py-1.5 text-sm hover:underline" style={{ color: "var(--danger)" }}>
                Remove
              </button>
            </div>
          </div>
        ) : (
          <div>
            <p className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>Connect your exchange API to automatically sync transactions.</p>
            <button onClick={() => setShowConnForm(true)} className="px-3 py-1.5 text-white rounded text-sm transition-colors" style={{ backgroundColor: "var(--accent)" }}>
              Connect API
            </button>
          </div>
        )}

        {exchangeSyncResult && (
          <div className="mt-3 bg-success-subtle rounded-lg p-3 text-sm" style={{ border: "1px solid rgba(34, 197, 94, 0.2)" }}>
            <div className="font-medium mb-1" style={{ color: "var(--success)" }}>Sync Complete</div>
            <div className="flex gap-4">
              <span style={{ color: "var(--success)" }}>{exchangeSyncResult.imported} imported</span>
              <span style={{ color: "var(--text-muted)" }}>{exchangeSyncResult.skipped} skipped</span>
              {exchangeSyncResult.errors > 0 && <span style={{ color: "var(--danger)" }}>{exchangeSyncResult.errors} errors</span>}
            </div>
            {exchangeSyncResult.error_messages.length > 0 && (
              <div className="mt-2 text-xs" style={{ color: "var(--danger)" }}>
                {exchangeSyncResult.error_messages.map((msg, i) => <div key={i}>{msg}</div>)}
              </div>
            )}
          </div>
        )}
        {exchangeSyncError && (
          <div className="mt-3 bg-danger-subtle rounded-lg p-3 text-sm" style={{ color: "var(--danger)", border: "1px solid rgba(239, 68, 68, 0.2)" }}>
            {exchangeSyncError}
          </div>
        )}
      </div>

      {/* Connection form modal */}
      {showConnForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <form onSubmit={handleSaveConnection} className="glass-card p-6 max-w-sm mx-4 space-y-3" style={{ background: "var(--bg-elevated)" }}>
            <h3 className="font-semibold" style={{ color: "var(--text-primary)" }}>Exchange API Connection</h3>
            <div>
              <label className="text-xs block mb-1" style={{ color: "var(--text-muted)" }}>Exchange</label>
              <select value={connType} onChange={(e) => setConnType(e.target.value)} className="rounded px-2 py-1.5 text-sm w-full">
                <option value="coinbase">Coinbase</option>
              </select>
            </div>
            <div>
              <label className="text-xs block mb-1" style={{ color: "var(--text-muted)" }}>API Key</label>
              <input type="password" value={connApiKey} onChange={(e) => setConnApiKey(e.target.value)} required className="rounded px-2 py-1.5 text-sm w-full" />
            </div>
            <div>
              <label className="text-xs block mb-1" style={{ color: "var(--text-muted)" }}>API Secret</label>
              <input type="password" value={connApiSecret} onChange={(e) => setConnApiSecret(e.target.value)} required className="rounded px-2 py-1.5 text-sm w-full" />
            </div>
            <div className="flex gap-2 justify-end">
              <button type="button" onClick={() => setShowConnForm(false)} className="px-3 py-1.5 rounded text-sm" style={{ backgroundColor: "var(--bg-surface-hover)", color: "var(--text-secondary)" }}>
                Cancel
              </button>
              <button type="submit" className="px-3 py-1.5 text-white rounded text-sm transition-colors" style={{ backgroundColor: "var(--accent)" }}>
                Save
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
