import { fmt } from "./Form8949View";

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function ScheduleDView({ data }: { data: any }) {
  return (
    <div className="glass-card p-5">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left" style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-secondary)" }}>
            <th className="px-3 py-2">Line</th>
            <th className="px-3 py-2">Description</th>
            <th className="px-3 py-2 text-right">Proceeds</th>
            <th className="px-3 py-2 text-right">Cost Basis</th>
            <th className="px-3 py-2 text-right">Gain/Loss</th>
          </tr>
        </thead>
        <tbody>
          {data.lines?.map((l: any) => {
            const gl = parseFloat(l.gain_loss);
            const isSummary = ["7", "15", "16"].includes(l.line);
            return (
              <tr
                key={l.line}
                style={{
                  borderBottom: "1px solid var(--border-subtle)",
                  backgroundColor: isSummary ? "var(--bg-surface-hover)" : "transparent",
                  fontWeight: isSummary ? 600 : 400,
                  color: "var(--text-primary)",
                }}
              >
                <td className="px-3 py-2">{l.line}</td>
                <td className="px-3 py-2">{l.description}</td>
                <td className="px-3 py-2 text-right">${fmt(l.proceeds)}</td>
                <td className="px-3 py-2 text-right">${fmt(l.cost_basis)}</td>
                <td className="px-3 py-2 text-right" style={{ color: gl >= 0 ? "var(--success)" : "var(--danger)" }}>
                  ${fmt(l.gain_loss)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="mt-4 text-sm" style={{ color: "var(--text-secondary)" }}>
        <span className="mr-6">Net Short-Term: <strong style={{ color: "var(--text-primary)" }}>${fmt(data.net_short_term)}</strong></span>
        <span className="mr-6">Net Long-Term: <strong style={{ color: "var(--text-primary)" }}>${fmt(data.net_long_term)}</strong></span>
        <span>Combined: <strong style={{ color: "var(--text-primary)" }}>${fmt(data.combined_net)}</strong></span>
      </div>
    </div>
  );
}
