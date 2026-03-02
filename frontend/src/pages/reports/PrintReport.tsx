import { fmt } from "./Form8949View";

/* eslint-disable @typescript-eslint/no-explicit-any */
export function openPrintWindow(taxYear: number, f8949: any, schedD: any, summary: any) {
  const fmtDate = (d: string) => new Date(d).toLocaleDateString();
  const glColor = (v: string | number) => (typeof v === "string" ? parseFloat(v) : v) >= 0 ? "#16a34a" : "#dc2626";
  const pf = (v: string | number) => fmt(v);

  // --- Form 8949 HTML ---
  function build8949Section(label: string, rows: any[], totals: any) {
    if (!rows || rows.length === 0) return `<p style="color:#888;font-size:12px;">No rows</p>`;

    const assetOrder: string[] = [];
    const groups: Record<string, any[]> = {};
    for (const r of rows) {
      const parts = (r.description as string).split(" ");
      const asset = parts.length >= 2 ? parts[parts.length - 1] : r.description;
      if (!groups[asset]) { groups[asset] = []; assetOrder.push(asset); }
      groups[asset].push(r);
    }

    let bodyRows = "";
    for (const asset of assetOrder) {
      const group = groups[asset];
      for (const r of group) {
        const parts = (r.description as string).split(" ");
        const units = parts.length >= 2 ? parts.slice(0, -1).join(" ") : r.description;
        bodyRows += `<tr>
          <td>${asset}</td><td class="r">${units}</td>
          <td>${fmtDate(r.date_acquired)}</td><td>${fmtDate(r.date_sold)}</td>
          <td class="r">$${pf(r.proceeds)}</td><td class="r">$${pf(r.cost_basis)}</td>
          <td class="r" style="color:${glColor(r.gain_loss)}">$${pf(r.gain_loss)}</td>
          <td>${r.checkbox_category}</td></tr>`;
      }
      if (group.length > 1) {
        const su = group.reduce((s: number, r: any) => s + parseFloat((r.description as string).split(" ").slice(0, -1).join("")), 0);
        const sp = group.reduce((s: number, r: any) => s + parseFloat(r.proceeds), 0);
        const sb = group.reduce((s: number, r: any) => s + parseFloat(r.cost_basis), 0);
        const sg = group.reduce((s: number, r: any) => s + parseFloat(r.gain_loss), 0);
        bodyRows += `<tr class="subtotal">
          <td>${asset} Subtotal</td><td class="r">${su}</td>
          <td></td><td></td>
          <td class="r">$${pf(sp)}</td><td class="r">$${pf(sb)}</td>
          <td class="r" style="color:${glColor(sg)}">$${pf(sg)}</td>
          <td></td></tr>`;
      }
    }

    const tgl = totals ? parseFloat(totals.gain_loss) : 0;
    const totalsRow = totals ? `<tr class="total">
      <td>Totals</td><td></td><td></td><td></td>
      <td class="r">$${pf(totals.proceeds)}</td><td class="r">$${pf(totals.cost_basis)}</td>
      <td class="r" style="color:${glColor(tgl)}">$${pf(totals.gain_loss)}</td>
      <td></td></tr>` : "";

    return `<h3>${label}</h3>
    <table><thead><tr>
      <th>Asset</th><th class="r">Units</th><th>Acquired</th><th>Sold</th>
      <th class="r">Proceeds</th><th class="r">Cost Basis</th><th class="r">Gain/Loss</th><th>Box</th>
    </tr></thead><tbody>${bodyRows}</tbody><tfoot>${totalsRow}</tfoot></table>`;
  }

  const f8949Html = `
    <div class="page-break">
      <h2>Form 8949 &mdash; Tax Year ${taxYear}</h2>
      ${build8949Section("Part I &mdash; Short-Term Capital Gains and Losses", f8949.short_term_rows, f8949.short_term_totals)}
      ${build8949Section("Part II &mdash; Long-Term Capital Gains and Losses", f8949.long_term_rows, f8949.long_term_totals)}
    </div>`;

  // --- Schedule D HTML ---
  let schedDRows = "";
  for (const l of (schedD.lines || [])) {
    const isSummary = ["7", "15", "16"].includes(l.line);
    const cls = isSummary ? ' class="total"' : "";
    schedDRows += `<tr${cls}>
      <td>${l.line}</td><td>${l.description}</td>
      <td class="r">$${pf(l.proceeds)}</td><td class="r">$${pf(l.cost_basis)}</td>
      <td class="r" style="color:${glColor(l.gain_loss)}">$${pf(l.gain_loss)}</td></tr>`;
  }
  const schedDHtml = `
    <div class="page-break">
      <h2>Schedule D &mdash; Tax Year ${taxYear}</h2>
      <table><thead><tr>
        <th>Line</th><th>Description</th><th class="r">Proceeds</th><th class="r">Cost Basis</th><th class="r">Gain/Loss</th>
      </tr></thead><tbody>${schedDRows}</tbody></table>
      <div class="sched-d-footer">
        <span>Net Short-Term: <strong>$${pf(schedD.net_short_term)}</strong></span>
        <span>Net Long-Term: <strong>$${pf(schedD.net_long_term)}</strong></span>
        <span>Combined: <strong>$${pf(schedD.combined_net)}</strong></span>
      </div>
    </div>`;

  // --- Tax Summary HTML ---
  function summarySection(title: string, rows: [string, string, boolean?][]) {
    let html = `<h3>${title}</h3>`;
    for (const [label, val, isTotal] of rows) {
      const num = parseFloat(val);
      const color = isTotal ? (num >= 0 ? "#16a34a" : "#dc2626") : "#111";
      const weight = isTotal ? "font-weight:600;" : "";
      html += `<div class="summary-row" style="${weight}">
        <span class="summary-label">${label}</span>
        <span style="color:${color}">$${pf(val)}</span></div>`;
    }
    return html;
  }

  const capitalGains: [string, string, boolean?][] = [
    ["Total Proceeds", summary.total_proceeds],
    ["Total Cost Basis", summary.total_cost_basis],
    ["Short-Term Gains", summary.short_term_gains],
    ["Short-Term Losses", summary.short_term_losses],
    ["Long-Term Gains", summary.long_term_gains],
    ["Long-Term Losses", summary.long_term_losses],
    ["Net Gain/Loss", summary.net_gain_loss, true],
  ];
  const income: [string, string, boolean?][] = [
    ["Staking Rewards", summary.staking_income],
    ["Airdrops", summary.airdrop_income],
    ["Forks", summary.fork_income],
    ["Mining", summary.mining_income],
    ["Interest", summary.interest_income],
    ["Other Income", summary.other_income],
    ["Total Income", summary.total_income, true],
  ];
  const expenses: [string, string, boolean?][] = [
    ["Cost / Gifts / Lost", summary.total_cost_expenses],
    ["Transfer Fees", summary.transfer_fees],
    ["Total Fees", summary.total_fees_usd, true],
  ];

  let eoyHtml = "";
  const balances = summary.eoy_balances || [];
  if (balances.length > 0) {
    let bRows = "";
    for (const b of balances) {
      const assetLabel = b.name ? `${b.name} - ${b.symbol}` : b.symbol;
      const mv = b.market_value_usd ? `$${pf(b.market_value_usd)}` : "\u2014";
      bRows += `<tr><td>${assetLabel}</td>
        <td class="r">${b.quantity}</td><td class="r">$${pf(b.cost_basis_usd)}</td><td class="r">${mv}</td></tr>`;
    }
    eoyHtml = `<h3>End of Year Balances</h3>
      <table><thead><tr><th>Asset</th><th class="r">Quantity</th><th class="r">Cost Basis</th><th class="r">Market Value (12/31)</th></tr></thead>
      <tbody>${bRows}</tbody></table>`;
  }

  const summaryHtml = `
    <div>
      <h2>Tax Summary &mdash; Tax Year ${taxYear}</h2>
      ${summarySection("Capital Gains Summary", capitalGains)}
      ${summarySection("Income Summary", income)}
      ${summarySection("Expenses", expenses)}
      ${eoyHtml}
    </div>`;

  // --- Assemble full document ---
  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Tax Reports ${taxYear}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 11px; color: #111; padding: 20px; }
  h2 { font-size: 16px; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 2px solid #333; }
  h3 { font-size: 13px; margin: 14px 0 6px; color: #333; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
  th, td { padding: 4px 8px; text-align: left; border-bottom: 1px solid #ddd; }
  th { font-weight: 600; border-bottom: 2px solid #999; font-size: 10px; text-transform: uppercase; color: #555; }
  .r { text-align: right; }
  tr.subtotal { background: #f5f5f5; font-weight: 600; font-size: 10px; }
  tr.subtotal td { border-bottom: 2px solid #ccc; }
  tr.total { font-weight: 700; }
  tr.total td { border-top: 2px solid #333; border-bottom: none; }
  tfoot tr.total td { border-top: 2px solid #333; }
  .summary-row { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #eee; }
  .summary-label { color: #555; }
  .sched-d-footer { margin-top: 8px; font-size: 12px; color: #555; display: flex; gap: 24px; }
  .sched-d-footer strong { color: #111; }
  .page-break { page-break-after: always; }
  @media print {
    body { padding: 0; }
    .page-break { page-break-after: always; }
  }
</style></head><body>
${f8949Html}
${schedDHtml}
${summaryHtml}
</body></html>`;

  const w = window.open("", "_blank");
  if (w) {
    w.document.write(html);
    w.document.close();
    setTimeout(() => w.print(), 300);
  }
}
