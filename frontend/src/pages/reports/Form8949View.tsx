import React from "react";
import { formatNumber as fmt } from "../../utils/format";

export { fmt };

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function Form8949View({ data }: { data: any }) {
  return (
    <div>
      {["short_term_rows", "long_term_rows"].map((section) => (
        <div key={section} className="mb-6">
          <h3 className="font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
            {section === "short_term_rows" ? "Part I \u2014 Short-Term" : "Part II \u2014 Long-Term"}
          </h3>
          {data[section]?.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>No rows</p>
          ) : (
            <table className="w-full text-sm glass-card">
              <thead>
                <tr className="text-left" style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
                  <th className="px-3 py-2">Asset</th>
                  <th className="px-3 py-2 text-right">Units</th>
                  <th className="px-3 py-2">Acquired</th>
                  <th className="px-3 py-2">Sold</th>
                  <th className="px-3 py-2 text-right">Proceeds</th>
                  <th className="px-3 py-2 text-right">Cost Basis</th>
                  <th className="px-3 py-2 text-right">Gain/Loss</th>
                  <th className="px-3 py-2">Box</th>
                </tr>
              </thead>
              {(() => {
                const rows: any[] = data[section] || [];
                const assetOrder: string[] = [];
                const groups: Record<string, any[]> = {};
                for (const r of rows) {
                  const parts = (r.description as string).split(" ");
                  const asset = parts.length >= 2 ? parts[parts.length - 1] : r.description;
                  if (!groups[asset]) {
                    groups[asset] = [];
                    assetOrder.push(asset);
                  }
                  groups[asset].push(r);
                }

                return (
                  <>
                    <tbody>
                      {assetOrder.map((asset) => {
                        const group = groups[asset];
                        const subtotalUnits = group.reduce((sum: number, r: any) => {
                          const parts = (r.description as string).split(" ");
                          return sum + parseFloat(parts.length >= 2 ? parts.slice(0, -1).join("") : "0");
                        }, 0);
                        const subtotalProceeds = group.reduce((sum: number, r: any) => sum + parseFloat(r.proceeds), 0);
                        const subtotalBasis = group.reduce((sum: number, r: any) => sum + parseFloat(r.cost_basis), 0);
                        const subtotalGl = group.reduce((sum: number, r: any) => sum + parseFloat(r.gain_loss), 0);

                        return (
                          <React.Fragment key={asset}>
                            {group.map((r: any, i: number) => {
                              const gl = parseFloat(r.gain_loss);
                              const parts = (r.description as string).split(" ");
                              const units = parts.length >= 2 ? parts.slice(0, -1).join(" ") : r.description;
                              return (
                                <tr key={`${asset}-${i}`} style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
                                  <td className="px-3 py-2">{asset}</td>
                                  <td className="px-3 py-2 text-right">{units}</td>
                                  <td className="px-3 py-2">{new Date(r.date_acquired).toLocaleDateString()}</td>
                                  <td className="px-3 py-2">{new Date(r.date_sold).toLocaleDateString()}</td>
                                  <td className="px-3 py-2 text-right">${fmt(r.proceeds)}</td>
                                  <td className="px-3 py-2 text-right">${fmt(r.cost_basis)}</td>
                                  <td className="px-3 py-2 text-right" style={{ color: gl >= 0 ? "var(--success)" : "var(--danger)" }}>
                                    ${fmt(r.gain_loss)}
                                  </td>
                                  <td className="px-3 py-2">{r.checkbox_category}</td>
                                </tr>
                              );
                            })}
                            {group.length > 1 && (
                              <tr style={{ borderBottom: "2px solid var(--border-default)", backgroundColor: "var(--bg-surface-hover)", fontWeight: 600, color: "var(--text-primary)" }}>
                                <td className="px-3 py-1 text-xs" style={{ color: "var(--text-secondary)" }}>{asset} Subtotal</td>
                                <td className="px-3 py-1 text-right">{subtotalUnits}</td>
                                <td className="px-3 py-1"></td>
                                <td className="px-3 py-1"></td>
                                <td className="px-3 py-1 text-right">${fmt(subtotalProceeds)}</td>
                                <td className="px-3 py-1 text-right">${fmt(subtotalBasis)}</td>
                                <td className="px-3 py-1 text-right" style={{ color: subtotalGl >= 0 ? "var(--success)" : "var(--danger)" }}>
                                  ${fmt(subtotalGl)}
                                </td>
                                <td className="px-3 py-1"></td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </tbody>
                    {(() => {
                      const totalsKey = section === "short_term_rows" ? "short_term_totals" : "long_term_totals";
                      const totals = data[totalsKey];
                      if (!totals) return null;
                      const totalGl = parseFloat(totals.gain_loss);
                      return (
                        <tfoot>
                          <tr style={{ borderTop: "2px solid var(--border-default)", fontWeight: 600, color: "var(--text-primary)" }}>
                            <td className="px-3 py-2">Totals</td>
                            <td className="px-3 py-2"></td>
                            <td className="px-3 py-2"></td>
                            <td className="px-3 py-2"></td>
                            <td className="px-3 py-2 text-right">${fmt(totals.proceeds)}</td>
                            <td className="px-3 py-2 text-right">${fmt(totals.cost_basis)}</td>
                            <td className="px-3 py-2 text-right" style={{ color: totalGl >= 0 ? "var(--success)" : "var(--danger)" }}>
                              ${fmt(totals.gain_loss)}
                            </td>
                            <td className="px-3 py-2"></td>
                          </tr>
                        </tfoot>
                      );
                    })()}
                  </>
                );
              })()}
            </table>
          )}
        </div>
      ))}
    </div>
  );
}
