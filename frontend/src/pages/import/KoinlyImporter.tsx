import { useState } from "react";
import { Link } from "react-router-dom";
import {
  uploadKoinly,
  confirmKoinlyImport,
  KoinlyPreviewResponse,
  KoinlyConfirmResponse,
} from "../../api/client";
import LoadingSpinner from "../../components/LoadingSpinner";
import ErrorBanner from "../../components/ErrorBanner";

type KoinlyStep = "upload" | "preview" | "importing" | "done";

export default function KoinlyImportTab() {
  const [step, setStep] = useState<KoinlyStep>("upload");
  const [walletsFile, setWalletsFile] = useState<File | null>(null);
  const [transactionsFile, setTransactionsFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<KoinlyPreviewResponse | null>(null);
  const [result, setResult] = useState<KoinlyConfirmResponse | null>(null);
  const [walletMapping, setWalletMapping] = useState<Record<string, number | "new">>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function handleUpload() {
    if (!walletsFile || !transactionsFile) return;
    setLoading(true);
    setError("");
    setWalletMapping({});
    uploadKoinly(walletsFile, transactionsFile)
      .then((r) => {
        setPreview(r.data);
        setStep("preview");
      })
      .catch((e) => setError(e.response?.data?.detail || "Upload failed"))
      .finally(() => setLoading(false));
  }

  const allWalletsMapped = preview
    ? preview.wallets.every((w) => walletMapping[w.koinly_id] !== undefined)
    : false;

  function handleConfirm() {
    setStep("importing");
    setError("");
    confirmKoinlyImport(walletMapping)
      .then((r) => {
        setResult(r.data);
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
        {(["upload", "preview", "done"] as KoinlyStep[]).map((s, i) => (
          <span
            key={s}
            className="px-3 py-1 rounded-full"
            style={{
              backgroundColor: step === s ? "var(--accent)" : "var(--bg-surface-hover)",
              color: step === s ? "white" : "var(--text-muted)",
            }}
          >
            {i + 1}. {s}
          </span>
        ))}
      </div>

      {error && <ErrorBanner message={error} />}

      {/* Step 1: Upload files */}
      {step === "upload" && (
        <div className="glass-card p-5 max-w-lg">
          <h2 className="font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Upload Koinly CSV Files</h2>
          <div className="text-sm mb-4 p-3 rounded" style={{ backgroundColor: "rgba(99, 102, 241, 0.08)", color: "var(--text-secondary)" }}>
            To generate these files, log into{" "}
            <a href="https://app.koinly.io" target="_blank" rel="noopener noreferrer" className="underline" style={{ color: "var(--accent)" }}>Koinly</a>,
            go to Transactions, open the browser console, and paste the{" "}
            <code className="text-xs px-1 rounded" style={{ backgroundColor: "var(--bg-surface-hover)" }}>scraper.js</code>{" "}
            script from the <code className="text-xs px-1 rounded" style={{ backgroundColor: "var(--bg-surface-hover)" }}>koinly-scraper</code> folder.
            It will download <strong>koinly_wallets.csv</strong> and <strong>koinly_transactions.csv</strong> automatically.
            See the{" "}
            <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="underline" style={{ color: "var(--accent)" }}>koinly-scraper README</a>{" "}
            for full instructions.
          </div>

          <div className="space-y-4 mb-4">
            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: "var(--text-primary)" }}>Wallets CSV</label>
              <div className="rounded-lg p-4" style={{ border: "2px dashed var(--border-default)" }}>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setWalletsFile(e.target.files?.[0] || null)}
                  className="text-sm"
                />
                {walletsFile && (
                  <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                    {walletsFile.name} ({(walletsFile.size / 1024).toFixed(1)} KB)
                  </p>
                )}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: "var(--text-primary)" }}>Transactions CSV</label>
              <div className="rounded-lg p-4" style={{ border: "2px dashed var(--border-default)" }}>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setTransactionsFile(e.target.files?.[0] || null)}
                  className="text-sm"
                />
                {transactionsFile && (
                  <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                    {transactionsFile.name} ({(transactionsFile.size / 1024).toFixed(1)} KB)
                  </p>
                )}
              </div>
            </div>
          </div>

          <div className="flex gap-2">
            <button
              disabled={!walletsFile || !transactionsFile || loading}
              onClick={handleUpload}
              className="px-4 py-2 rounded text-sm disabled:opacity-40 transition-colors cursor-pointer"
              style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
            >
              {loading ? "Parsing..." : "Upload & Preview"}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Preview */}
      {step === "preview" && preview && (
        <div className="glass-card p-5">
          <h2 className="font-semibold mb-4" style={{ color: "var(--text-primary)" }}>Import Preview</h2>

          {/* Wallet mapping */}
          <div className="mb-4">
            <h3 className="text-sm font-medium mb-2" style={{ color: "var(--text-primary)" }}>
              Map Koinly Wallets to Your Wallets
            </h3>
            <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
              Each Koinly wallet will be added as an account under the wallet you select.
            </p>
          </div>

          {preview.wallets.length > 0 && (
            <div className="overflow-x-auto mb-4 max-h-64 overflow-y-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="text-left" style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
                    <th className="px-2 py-1">Koinly Wallet</th>
                    <th className="px-2 py-1">Type</th>
                    <th className="px-2 py-1">Blockchain</th>
                    <th className="px-2 py-1">Assign To Wallet</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.wallets.map((w) => (
                    <tr
                      key={w.koinly_id}
                      style={{
                        borderBottom: "1px solid var(--border-subtle)",
                        color: "var(--text-primary)",
                      }}
                    >
                      <td className="px-2 py-1">
                        <div>{w.name}</div>
                        <div className="text-xs" style={{ color: "var(--text-muted)" }}>ID: {w.koinly_id}</div>
                      </td>
                      <td className="px-2 py-1">{w.mapped_type}</td>
                      <td className="px-2 py-1">{w.blockchain || "\u2014"}</td>
                      <td className="px-2 py-1">
                        <select
                          className="text-xs rounded px-2 py-1 w-full"
                          style={{
                            backgroundColor: "var(--bg-surface)",
                            border: "1px solid var(--border-default)",
                            color: "var(--text-primary)",
                          }}
                          value={
                            walletMapping[w.koinly_id] === "new"
                              ? "new"
                              : walletMapping[w.koinly_id] !== undefined
                                ? String(walletMapping[w.koinly_id])
                                : ""
                          }
                          onChange={(e) => {
                            const val = e.target.value;
                            setWalletMapping((prev) => ({
                              ...prev,
                              [w.koinly_id]: val === "new" ? "new" : Number(val),
                            }));
                          }}
                        >
                          <option value="" disabled>Select wallet...</option>
                          <option value="new">+ Create New Wallet</option>
                          {preview.existing_wallets_list.map((ew) => (
                            <option key={ew.id} value={ew.id}>
                              {ew.name} ({ew.type})
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Transaction summary */}
          <div className="mb-4">
            <h3 className="text-sm font-medium mb-2" style={{ color: "var(--text-primary)" }}>Transactions</h3>
            <div className="flex gap-4 text-sm flex-wrap" style={{ color: "var(--text-secondary)" }}>
              <span>Total: <strong style={{ color: "var(--text-primary)" }}>{preview.total_transactions}</strong></span>
              <span style={{ color: "var(--success)" }}>Valid: <strong>{preview.valid_transactions}</strong></span>
              <span style={{ color: "var(--text-muted)" }}>Duplicates: <strong>{preview.duplicate_transactions}</strong></span>
              <span style={{ color: "var(--danger)" }}>Errors: <strong>{preview.error_transactions}</strong></span>
              {preview.warning_transactions > 0 && (
                <span style={{ color: "var(--warning)" }}>Warnings: <strong>{preview.warning_transactions}</strong></span>
              )}
            </div>
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
              disabled={!allWalletsMapped || preview.valid_transactions === 0}
              className="px-4 py-2 rounded text-sm disabled:opacity-40 transition-colors cursor-pointer"
              style={{ border: "1px solid var(--success)", color: "var(--success)" }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--success)"; e.currentTarget.style.color = "#fff"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--success)"; }}
            >
              Confirm Import ({preview.wallets.length} accounts, {preview.valid_transactions} transactions)
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Importing */}
      {step === "importing" && <LoadingSpinner message="Importing Koinly data..." />}

      {/* Step 4: Done */}
      {step === "done" && result && (
        <div className="glass-card p-5 max-w-md">
          <h2 className="font-semibold mb-3" style={{ color: "var(--success)" }}>Import Complete</h2>
          <div className="text-sm space-y-1 mb-4" style={{ color: "var(--text-primary)" }}>
            <p>Wallets created: <strong>{result.wallets_created}</strong></p>
            <p>Wallets reused (existing): <strong>{result.wallets_skipped}</strong></p>
            <p>Accounts created: <strong>{result.accounts_created}</strong></p>
            <p>Transactions imported: <strong>{result.transactions_imported}</strong></p>
            <p>Transactions skipped: <strong>{result.transactions_skipped}</strong></p>
          </div>
          <div className="flex gap-2">
            <Link
              to="/wallets"
              className="px-4 py-2 rounded text-sm transition-colors cursor-pointer"
              style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
            >
              View Wallets
            </Link>
            <Link
              to="/transactions"
              className="px-4 py-2 rounded text-sm"
              style={{ border: "1px solid var(--border-default)", color: "var(--text-secondary)" }}
            >
              View Transactions
            </Link>
            <button
              onClick={() => {
                setStep("upload");
                setWalletsFile(null);
                setTransactionsFile(null);
                setPreview(null);
                setResult(null);
                setWalletMapping({});
              }}
              className="px-4 py-2 rounded text-sm"
              style={{ border: "1px solid var(--border-default)", color: "var(--text-secondary)" }}
            >
              Import Again
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
