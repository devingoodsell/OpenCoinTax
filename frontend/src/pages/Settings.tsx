import { useState } from "react";
import { fetchSettings, updateSettings, resetDatabase } from "../api/client";
import { useApiQuery } from "../hooks/useApiQuery";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";

export default function Settings() {
  const { data: initialSettings, loading, error: loadError } = useApiQuery(
    () => fetchSettings().then((r) => r.data as Record<string, string>),
    [],
  );
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [initialized, setInitialized] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [resetting, setResetting] = useState(false);

  if (initialSettings && !initialized) {
    setSettings(initialSettings);
    setInitialized(true);
  }

  function handleSave() {
    setSaved(false);
    setError("");
    updateSettings(settings)
      .then(() => setSaved(true))
      .catch((e) => setError(e.response?.data?.detail || "Save failed"));
  }

  function update(key: string, value: string) {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  if (loading) return <LoadingSpinner />;

  return (
    <div className="max-w-lg">
      <h1 className="text-2xl font-bold mb-6" style={{ color: "var(--text-primary)" }}>Settings</h1>

      {(loadError || error) && <ErrorBanner message={loadError || error} />}
      {saved && (
        <div className="bg-success-subtle rounded-lg p-3 text-sm mb-4" style={{ color: "var(--success)", border: "1px solid rgba(34, 197, 94, 0.2)" }}>
          Settings saved.
        </div>
      )}

      <div className="glass-card p-5 mb-6">
        <div className="mb-4">
          <label className="text-sm block mb-1" style={{ color: "var(--text-secondary)" }}>Default Cost Basis Method</label>
          <select
            value={settings.default_cost_basis_method || "fifo"}
            onChange={(e) => update("default_cost_basis_method", e.target.value)}
            className="rounded px-2 py-1.5 text-sm w-full"
          >
            <option value="fifo">FIFO</option>
            <option value="lifo">LIFO</option>
            <option value="hifo">HIFO</option>
          </select>
        </div>

        <div className="mb-4">
          <label className="text-sm block mb-1" style={{ color: "var(--text-secondary)" }}>Base Currency</label>
          <input
            value={settings.base_currency || "USD"}
            onChange={(e) => update("base_currency", e.target.value)}
            className="rounded px-2 py-1.5 text-sm w-full"
          />
        </div>

        <div className="mb-4">
          <label className="text-sm block mb-1" style={{ color: "var(--text-secondary)" }}>Long-Term Threshold (days)</label>
          <input
            type="number"
            value={settings.long_term_threshold_days || "365"}
            onChange={(e) => update("long_term_threshold_days", e.target.value)}
            className="rounded px-2 py-1.5 text-sm w-full"
          />
        </div>

        <button
          onClick={handleSave}
          className="px-4 py-2 rounded text-sm transition-colors cursor-pointer"
          style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
        >
          Save Settings
        </button>
      </div>

      <div className="glass-card p-5">
        <h2 className="font-semibold mb-3" style={{ color: "var(--danger)" }}>Danger Zone</h2>
        <button
          onClick={() => {
            if (!window.confirm("This will delete ALL wallets, accounts, transactions, and tax data. Are you sure?")) return;
            setResetting(true);
            setError("");
            resetDatabase()
              .then(() => window.location.reload())
              .catch((e) => setError(e.response?.data?.detail || "Reset failed"))
              .finally(() => setResetting(false));
          }}
          disabled={resetting}
          className="px-4 py-2 rounded text-sm disabled:opacity-50 transition-colors"
          style={{ border: "1px solid var(--danger)", color: "var(--danger)" }}
        >
          {resetting ? "Resetting..." : "Reset Database"}
        </button>
        <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
          Permanently deletes all wallets, accounts, transactions, and tax data. This cannot be undone.
        </p>
      </div>
    </div>
  );
}
