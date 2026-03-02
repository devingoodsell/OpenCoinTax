import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { fetchImportLogs, deleteImport } from "../../api/client";
import { useApiQuery } from "../../hooks/useApiQuery";
import CsvImport from "./CsvImporter";
import KoinlyImportTab from "./KoinlyImporter";

interface ImportLog {
  id: number;
  import_type: string;
  status: string;
  transactions_imported: number;
  transactions_skipped: number;
  started_at: string;
}

type ImportTab = "csv" | "coinbase" | "koinly";

export default function Import() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState<ImportTab>(
    tabParam === "koinly" ? "koinly" : tabParam === "coinbase" ? "coinbase" : "csv"
  );
  const { data: logs, refetch: loadLogs } = useApiQuery(
    () => fetchImportLogs().then((r) => (r.data.items || []) as ImportLog[]),
    [],
  );
  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function handleDeleteImport(log: ImportLog) {
    const ok = window.confirm(
      `Delete this import and its ${log.transactions_imported} transaction(s)? This will also recalculate your tax data.`
    );
    if (!ok) return;
    setDeletingId(log.id);
    try {
      await deleteImport(log.id);
      loadLogs();
    } catch {
      alert("Failed to delete import. Please try again.");
    } finally {
      setDeletingId(null);
    }
  }

  function switchTab(tab: ImportTab) {
    setActiveTab(tab);
    setSearchParams(tab === "csv" ? {} : { tab });
  }

  const tabs: { key: ImportTab; label: string; description: string }[] = [
    { key: "csv", label: "Ledger CSV Export", description: "Import from a Ledger Live CSV export" },
    { key: "coinbase", label: "Coinbase", description: "Import from a Coinbase CSV export" },
    { key: "koinly", label: "Koinly", description: "Import wallets and transactions from Koinly export" },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6" style={{ color: "var(--text-primary)" }}>
        Import
      </h1>

      {/* Tab selector */}
      <div
        className="flex gap-0 mb-6 rounded-lg overflow-hidden inline-flex"
        style={{ border: "1px solid var(--border-default)" }}
      >
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => switchTab(t.key)}
            className="px-5 py-2.5 text-sm font-medium transition-colors"
            style={{
              backgroundColor: activeTab === t.key ? "var(--accent)" : "var(--bg-surface)",
              color: activeTab === t.key ? "#fff" : "var(--text-secondary)",
              borderRight: t.key !== tabs[tabs.length - 1].key ? "1px solid var(--border-default)" : undefined,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "csv" && <CsvImport />}
      {activeTab === "coinbase" && <CsvImport />}
      {activeTab === "koinly" && <KoinlyImportTab />}

      {/* Import history — always visible */}
      {logs && logs.length > 0 && (
        <div className="mt-8">
          <h2 className="font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Import History</h2>
          <table className="w-full text-sm glass-card">
            <thead>
              <tr className="text-left" style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Imported</th>
                <th className="px-3 py-2">Skipped</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id} style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
                  <td className="px-3 py-2">{new Date(l.started_at).toLocaleDateString()}</td>
                  <td className="px-3 py-2">{l.import_type.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</td>
                  <td className="px-3 py-2">{l.status}</td>
                  <td className="px-3 py-2">{l.transactions_imported}</td>
                  <td className="px-3 py-2">{l.transactions_skipped}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => handleDeleteImport(l)}
                      disabled={deletingId === l.id}
                      className="text-xs px-2 py-1 rounded transition-colors"
                      style={{
                        color: "var(--text-danger, #ef4444)",
                        border: "1px solid var(--border-default)",
                        opacity: deletingId === l.id ? 0.5 : 1,
                        cursor: deletingId === l.id ? "not-allowed" : "pointer",
                      }}
                    >
                      {deletingId === l.id ? "Deleting..." : "Delete"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
