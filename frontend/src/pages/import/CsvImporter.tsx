import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { uploadCsv, confirmImport, fetchWallets } from "../../api/client";
import { useApiQuery } from "../../hooks/useApiQuery";
import LoadingSpinner from "../../components/LoadingSpinner";
import ErrorBanner from "../../components/ErrorBanner";

interface ParsedRow {
  row_number: number;
  status: string;
  error_message: string | null;
  datetime_utc: string | null;
  type: string | null;
  from_amount: string | null;
  from_asset: string | null;
  to_amount: string | null;
  to_asset: string | null;
  fee_amount: string | null;
  fee_asset: string | null;
  net_value_usd: string | null;
  description: string | null;
  tx_hash: string | null;
}

interface Wallet {
  id: number;
  name: string;
}

type CsvStep = "select-wallet" | "upload" | "preview" | "importing" | "done";

export default function CsvImport() {
  const [searchParams] = useSearchParams();
  const { data: wallets } = useApiQuery(
    () => fetchWallets().then((r) => {
      const items = Array.isArray(r.data) ? r.data : (r.data as any).items || [];
      return items as Wallet[];
    }),
    [],
  );
  const [step, setStep] = useState<CsvStep>("select-wallet");
  const [walletId, setWalletId] = useState<number>(() => {
    const preselect = searchParams.get("wallet");
    return preselect ? Number(preselect) : 0;
  });
  const [file, setFile] = useState<File | null>(null);
  const [detectedFormat, setDetectedFormat] = useState("");
  const [rows, setRows] = useState<ParsedRow[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [validRows, setValidRows] = useState(0);
  const [warningRows, setWarningRows] = useState(0);
  const [errorRows, setErrorRows] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ imported: number; skipped: number } | null>(null);

  function handleUpload() {
    if (!file) return;
    setLoading(true);
    setError("");
    uploadCsv(file)
      .then((r) => {
        setDetectedFormat(r.data.detected_format);
        setRows(r.data.rows);
        setTotalRows(r.data.total_rows);
        setValidRows(r.data.valid_rows);
        setWarningRows(r.data.warning_rows || 0);
        setErrorRows(r.data.error_rows);
        setStep("preview");
      })
      .catch((e) => setError(e.response?.data?.detail || "Upload failed"))
      .finally(() => setLoading(false));
  }

  function handleConfirm() {
    setStep("importing");
    setError("");
    const selectedRows = rows
      .filter((r) => r.status !== "error")
      .map((r) => r.row_number);
    confirmImport({ wallet_id: walletId, rows: selectedRows })
      .then((r) => {
        setResult({
          imported: r.data.transactions_imported,
          skipped: r.data.transactions_skipped,
        });
        setStep("done");
      })
      .catch((e) => {
        setError(e.response?.data?.detail || "Import failed");
        setStep("preview");
      });
  }

  return (
    <div>
      {/* Step indicator */}
      <div className="flex gap-2 mb-6 text-sm">
        {(["select-wallet", "upload", "preview", "done"] as CsvStep[]).map((s, i) => (
          <span
            key={s}
            className="px-3 py-1 rounded-full"
            style={{
              backgroundColor: step === s ? "var(--accent)" : "var(--bg-surface-hover)",
              color: step === s ? "white" : "var(--text-muted)",
            }}
          >
            {i + 1}. {s.replace("-", " ")}
          </span>
        ))}
      </div>

      {error && <ErrorBanner message={error} />}

      {/* Step 1: Select wallet */}
      {step === "select-wallet" && (
        <div className="glass-card p-5 max-w-md">
          <h2 className="font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Select Wallet</h2>
          <select
            value={walletId}
            onChange={(e) => setWalletId(Number(e.target.value))}
            className="w-full rounded px-2 py-2 text-sm mb-4"
          >
            <option value={0}>Choose a wallet...</option>
            {(wallets ?? []).map((w) => (
              <option key={w.id} value={w.id}>{w.name}</option>
            ))}
          </select>
          <button
            disabled={!walletId}
            onClick={() => setStep("upload")}
            className="px-4 py-2 rounded text-sm disabled:opacity-40 transition-colors cursor-pointer"
            style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
          >
            Next
          </button>
        </div>
      )}

      {/* Step 2: Upload file */}
      {step === "upload" && (
        <div className="glass-card p-5 max-w-md">
          <h2 className="font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Upload CSV</h2>
          <div className="rounded-lg p-8 text-center mb-4" style={{ border: "2px dashed var(--border-default)" }}>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="text-sm"
            />
            {file && <p className="text-sm mt-2" style={{ color: "var(--text-muted)" }}>{file.name} ({(file.size / 1024).toFixed(1)} KB)</p>}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setStep("select-wallet")}
              className="px-4 py-2 rounded text-sm"
              style={{ border: "1px solid var(--border-default)", color: "var(--text-secondary)" }}
            >
              Back
            </button>
            <button
              disabled={!file || loading}
              onClick={handleUpload}
              className="px-4 py-2 rounded text-sm disabled:opacity-40 transition-colors cursor-pointer"
              style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
            >
              {loading ? "Parsing..." : "Upload & Parse"}
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Preview */}
      {step === "preview" && (
        <div className="glass-card p-5">
          <h2 className="font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Preview</h2>
          <div className="flex gap-4 mb-4 text-sm flex-wrap" style={{ color: "var(--text-secondary)" }}>
            <span>Format: <strong style={{ color: "var(--text-primary)" }}>{detectedFormat === "ledger" ? "Ledger Live" : detectedFormat}</strong></span>
            <span>Total: <strong style={{ color: "var(--text-primary)" }}>{totalRows}</strong></span>
            <span style={{ color: "var(--success)" }}>Valid: <strong>{validRows}</strong></span>
            {warningRows > 0 && <span style={{ color: "var(--warning, #f59e0b)" }}>Skipped: <strong>{warningRows}</strong></span>}
            <span style={{ color: "var(--danger)" }}>Errors: <strong>{errorRows}</strong></span>
          </div>
          {detectedFormat === "ledger" && (
            <div className="text-sm mb-4 p-3 rounded" style={{ backgroundColor: "rgba(59, 130, 246, 0.1)", color: "var(--text-secondary)" }}>
              Ledger Live import will merge with existing transactions by matching transaction hashes.
              Existing records will be enriched with fee data and account information from Ledger.
            </div>
          )}

          <div className="overflow-x-auto max-h-80 overflow-y-auto mb-4">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="text-left" style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
                  <th className="px-2 py-1">#</th>
                  <th className="px-2 py-1">Status</th>
                  <th className="px-2 py-1">Date</th>
                  <th className="px-2 py-1">Type</th>
                  <th className="px-2 py-1">From</th>
                  <th className="px-2 py-1">To</th>
                  <th className="px-2 py-1">Error</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.row_number}
                    style={{
                      borderBottom: "1px solid var(--border-subtle)",
                      backgroundColor: r.status === "error" ? "rgba(239, 68, 68, 0.1)" : r.status === "warning" ? "rgba(245, 158, 11, 0.1)" : "transparent",
                      color: "var(--text-primary)",
                    }}
                  >
                    <td className="px-2 py-1">{r.row_number}</td>
                    <td className="px-2 py-1">{r.status}</td>
                    <td className="px-2 py-1">{r.datetime_utc ? new Date(r.datetime_utc).toLocaleDateString() : "\u2014"}</td>
                    <td className="px-2 py-1">{r.type ?? "\u2014"}</td>
                    <td className="px-2 py-1">{r.from_amount ? `${r.from_amount} ${r.from_asset ?? ""}` : "\u2014"}</td>
                    <td className="px-2 py-1">{r.to_amount ? `${r.to_amount} ${r.to_asset ?? ""}` : "\u2014"}</td>
                    <td className="px-2 py-1" style={{ color: "var(--danger)" }}>{r.error_message ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setStep("upload")}
              className="px-4 py-2 rounded text-sm"
              style={{ border: "1px solid var(--border-default)", color: "var(--text-secondary)" }}
            >
              Back
            </button>
            <button
              onClick={handleConfirm}
              disabled={validRows === 0}
              className="px-4 py-2 rounded text-sm disabled:opacity-40 transition-colors cursor-pointer"
              style={{ border: "1px solid var(--success)", color: "var(--success)" }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--success)"; e.currentTarget.style.color = "#fff"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--success)"; }}
            >
              Confirm Import ({validRows} rows)
            </button>
          </div>
        </div>
      )}

      {/* Step 4: Importing */}
      {step === "importing" && <LoadingSpinner message="Importing transactions..." />}

      {/* Step 5: Done */}
      {step === "done" && result && (
        <div className="glass-card p-5 max-w-md">
          <h2 className="font-semibold mb-3" style={{ color: "var(--success)" }}>Import Complete</h2>
          <div className="text-sm mb-4" style={{ color: "var(--text-primary)" }}>
            <p>New transactions imported: <strong>{result.imported}</strong></p>
            {detectedFormat === "ledger" ? (
              <p>Existing transactions enriched/skipped: <strong>{result.skipped}</strong></p>
            ) : (
              <p>Skipped (duplicates): <strong>{result.skipped}</strong></p>
            )}
          </div>
          <div className="flex gap-2">
            <Link
              to="/transactions"
              className="px-4 py-2 rounded text-sm transition-colors cursor-pointer"
              style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
            >
              View Transactions
            </Link>
            <button
              onClick={() => { setStep("select-wallet"); setFile(null); setRows([]); setResult(null); }}
              className="px-4 py-2 rounded text-sm"
              style={{ border: "1px solid var(--border-default)", color: "var(--text-secondary)" }}
            >
              Import More
            </button>
          </div>
        </div>
      )}

    </div>
  );
}
