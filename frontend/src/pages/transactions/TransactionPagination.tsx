import React, { useState } from "react";

function getPageNumbers(current: number, total: number): (number | "...")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: (number | "...")[] = [];
  pages.push(1);
  if (current > 3) pages.push("...");
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  for (let i = start; i <= end; i++) pages.push(i);
  if (current < total - 2) pages.push("...");
  if (total > 1) pages.push(total);
  return pages;
}

export default function StickyPagination({
  page,
  totalPages,
  total,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (p: number) => void;
}) {
  const [goToInput, setGoToInput] = useState("");
  const pageNums = getPageNumbers(page, totalPages);

  function handleGo() {
    const n = parseInt(goToInput, 10);
    if (n >= 1 && n <= totalPages) {
      onPageChange(n);
      setGoToInput("");
    }
  }

  const btnBase: React.CSSProperties = {
    minWidth: 32,
    height: 32,
    border: "1px solid var(--border-default)",
    color: "var(--text-secondary)",
    backgroundColor: "transparent",
  };
  const btnActive: React.CSSProperties = {
    ...btnBase,
    backgroundColor: "var(--accent)",
    borderColor: "var(--accent)",
    color: "#fff",
  };

  return (
    <div
      className="fixed bottom-0 left-0 right-0 flex items-center justify-between px-6 py-2.5 text-sm z-50"
      style={{
        backgroundColor: "var(--bg-surface)",
        borderTop: "1px solid var(--border-default)",
        backdropFilter: "blur(12px)",
      }}
    >
      <span style={{ color: "var(--text-muted)" }}>
        {total.toLocaleString()} transaction{total !== 1 ? "s" : ""}
      </span>

      <div className="flex items-center gap-1">
        <button
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="flex items-center justify-center rounded text-sm disabled:opacity-30 transition-colors"
          style={btnBase}
          title="Previous page"
        >
          ‹
        </button>

        {pageNums.map((p, i) =>
          p === "..." ? (
            <span key={`ellipsis-${i}`} className="px-1" style={{ color: "var(--text-muted)" }}>
              …
            </span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p)}
              className="flex items-center justify-center rounded text-sm font-medium transition-colors"
              style={p === page ? btnActive : btnBase}
            >
              {p}
            </button>
          )
        )}

        <button
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="flex items-center justify-center rounded text-sm disabled:opacity-30 transition-colors"
          style={btnBase}
          title="Next page"
        >
          ›
        </button>
      </div>

      <div className="flex items-center gap-2">
        <span style={{ color: "var(--text-muted)" }}>Go to page</span>
        <input
          type="number"
          min={1}
          max={totalPages}
          value={goToInput}
          onChange={(e) => setGoToInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleGo(); }}
          className="rounded px-2 py-1 text-sm text-center"
          style={{
            width: 56,
            backgroundColor: "var(--bg-base, var(--bg-surface))",
            color: "var(--text-primary)",
            border: "1px solid var(--border-default)",
          }}
        />
        <button
          onClick={handleGo}
          className="px-3 py-1 rounded text-sm font-medium transition-colors cursor-pointer"
          style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = "var(--accent)"; }}
        >
          Go
        </button>
      </div>
    </div>
  );
}
