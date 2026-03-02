import { useEffect, useState } from "react";
import { useTaxYear } from "../../hooks/useTaxYear";
import {
  fetchForm8949,
  downloadForm8949Csv,
  fetchScheduleD,
  fetchReportTaxSummary,
  recalculate,
  validateTax,
  compareMethods,
} from "../../api/client";
import LoadingSpinner from "../../components/LoadingSpinner";
import ErrorBanner from "../../components/ErrorBanner";
import Form8949View from "./Form8949View";
import ScheduleDView from "./ScheduleDView";
import SummaryView, { AuditView } from "./TaxSummaryView";
import { openPrintWindow } from "./PrintReport";

type Tab = "8949" | "schedule-d" | "summary" | "audit";

const YEARS = [2024, 2025, 2026];

export default function Reports() {
  const { taxYear, setTaxYear } = useTaxYear();
  const [tab, setTab] = useState<Tab>("8949");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);

  // Audit state
  const [auditChecks, setAuditChecks] = useState<{ check_name: string; status: string; details: string }[] | null>(null);
  const [auditAllPassed, setAuditAllPassed] = useState<boolean | null>(null);
  const [auditComparisons, setAuditComparisons] = useState<{ method: string; total_gains: string; total_losses: string; net_gain_loss: string; short_term_net: string; long_term_net: string }[] | null>(null);

  // Auto-generate reports when tax year changes (or on first load)
  useEffect(() => {
    setData(null);
    setAuditChecks(null);
    setAuditAllPassed(null);
    setAuditComparisons(null);
    setGenerating(true);
    setError("");
    recalculate(taxYear)
      .then(() => {
        if (tab === "audit") {
          setGenerating(false);
          return;
        }
        const fetcher =
          tab === "8949" ? fetchForm8949 : tab === "schedule-d" ? fetchScheduleD : fetchReportTaxSummary;
        return fetcher(taxYear).then((r) => setData(r.data));
      })
      .catch((e) => setError(e.response?.data?.detail || "Recalculation failed"))
      .finally(() => setGenerating(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taxYear]);

  function loadTab(t: Tab) {
    setTab(t);
    if (t === "audit") return;
    setLoading(true);
    setError("");
    const fetcher =
      t === "8949" ? fetchForm8949 : t === "schedule-d" ? fetchScheduleD : fetchReportTaxSummary;
    fetcher(taxYear)
      .then((r) => setData(r.data))
      .catch((e) => setError(e.response?.data?.detail || "Failed to load"))
      .finally(() => setLoading(false));
  }

  function runValidation() {
    setLoading(true);
    setError("");
    validateTax()
      .then((r) => {
        setAuditChecks(r.data.results);
        setAuditAllPassed(r.data.all_passed);
      })
      .catch((e) => setError(e.response?.data?.detail || "Validation failed"))
      .finally(() => setLoading(false));
  }

  function runComparison() {
    setLoading(true);
    setError("");
    compareMethods(taxYear)
      .then((r) => setAuditComparisons(r.data.comparisons))
      .catch((e) => setError(e.response?.data?.detail || "Comparison failed"))
      .finally(() => setLoading(false));
  }

  const [printing, setPrinting] = useState(false);

  function downloadCsv() {
    downloadForm8949Csv(taxYear).then((r) => {
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `form_8949_${taxYear}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  function printAllReports() {
    setPrinting(true);
    setError("");
    Promise.all([
      fetchForm8949(taxYear),
      fetchScheduleD(taxYear),
      fetchReportTaxSummary(taxYear),
    ])
      .then(([f8949Res, schedDRes, summaryRes]) => {
        openPrintWindow(taxYear, f8949Res.data, schedDRes.data, summaryRes.data);
      })
      .catch((e) => setError(e.response?.data?.detail || "Failed to load reports for printing"))
      .finally(() => setPrinting(false));
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>Reports —</h1>
          <select
            value={taxYear}
            onChange={(e) => setTaxYear(Number(e.target.value))}
            className="rounded px-2 py-1 text-lg font-bold"
            style={{
              backgroundColor: "var(--bg-surface)",
              color: "var(--text-primary)",
              border: "1px solid var(--border-default)",
            }}
          >
            {YEARS.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
        <div className="flex gap-2">
          <button
            onClick={downloadCsv}
            disabled={generating}
            className="px-4 py-2 rounded text-sm disabled:opacity-50 transition-colors cursor-pointer"
            style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
          >
            Download CSV
          </button>
          <button
            onClick={printAllReports}
            disabled={printing || generating}
            className="px-4 py-2 rounded text-sm disabled:opacity-50 transition-colors cursor-pointer"
            style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
          >
            {printing ? "Loading..." : "Print PDF"}
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 mb-4" style={{ borderBottom: "1px solid var(--border-default)" }}>
        {(["8949", "schedule-d", "summary", "audit"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => loadTab(t)}
            className="px-4 py-2 text-sm"
            style={{
              borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
              color: tab === t ? "var(--accent)" : "var(--text-muted)",
              fontWeight: tab === t ? 600 : 400,
            }}
          >
            {t === "8949" ? "Form 8949" : t === "schedule-d" ? "Schedule D" : t === "summary" ? "Tax Summary" : "Audit"}
          </button>
        ))}
      </div>

      {error && <ErrorBanner message={error} />}
      {(loading || generating) && <LoadingSpinner />}

      {!loading && !generating && !error && data && tab === "8949" && <Form8949View data={data} />}
      {!loading && !generating && !error && data && tab === "schedule-d" && <ScheduleDView data={data} />}
      {!loading && !generating && !error && data && tab === "summary" && <SummaryView data={data} />}

      {/* Audit tab */}
      {!loading && !generating && tab === "audit" && (
        <AuditView
          checks={auditChecks}
          allPassed={auditAllPassed}
          comparisons={auditComparisons}
          onRunValidation={runValidation}
          onRunComparison={runComparison}
        />
      )}
    </div>
  );
}
