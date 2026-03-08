import {
  ResponsiveContainer,
  AreaChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

function fmt(value: string | number, decimals = 2): string {
  return Number(value).toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const value = payload.find((p: any) => p.dataKey === "value")?.value;
  const costBasis = payload.find((p: any) => p.dataKey === "costBasis")?.value;
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs shadow-lg"
      style={{
        backgroundColor: "var(--bg-elevated)",
        border: "1px solid var(--border-default)",
        color: "var(--text-primary)",
      }}
    >
      <div style={{ color: "var(--text-muted)" }}>{label}</div>
      {value != null && (
        <div className="font-semibold mt-1" style={{ color: "var(--accent)" }}>
          Value: ${fmt(value)}
        </div>
      )}
      {costBasis != null && costBasis > 0 && (
        <div className="mt-0.5" style={{ color: "var(--warning, #eab308)" }}>
          Cost Basis: ${fmt(costBasis)}
        </div>
      )}
      {value != null && costBasis != null && costBasis > 0 && (
        <div className="mt-0.5" style={{ color: value >= costBasis ? "var(--success)" : "var(--danger)" }}>
          {value >= costBasis ? "+" : ""}${fmt(value - costBasis)} ({value >= costBasis ? "+" : ""}{((value - costBasis) / costBasis * 100).toFixed(1)}%)
        </div>
      )}
    </div>
  );
}

interface Props {
  chartData: { date: string; value: number; costBasis: number }[];
  priceDataStartDate?: string;
}

export default function PortfolioChart({ chartData, priceDataStartDate }: Props) {
  if (chartData.length === 0) {
    return (
      <div className="glass-card p-8 mb-4 text-center" style={{ color: "var(--text-muted)" }}>
        No chart data available. Portfolio value requires price history and tax lot calculation.
      </div>
    );
  }

  return (
    <div className="glass-card p-4 mb-4">
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.3} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "var(--text-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "var(--border-subtle)" }}
            tickFormatter={(d: string) => {
              const dt = new Date(d + "T00:00:00");
              const startYear = new Date(chartData[0].date + "T00:00:00").getFullYear();
              const endYear = new Date(chartData[chartData.length - 1].date + "T00:00:00").getFullYear();
              const multiYear = endYear > startYear;
              if (multiYear) {
                const m = dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                return `${m} '${String(dt.getFullYear()).slice(2)}`;
              }
              return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
            }}
            interval="preserveStartEnd"
            minTickGap={50}
          />
          <YAxis
            tick={{ fill: "var(--text-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => v >= 1000 ? `$${(v / 1000).toFixed(0)}k` : `$${v}`}
            width={60}
          />
          <Tooltip content={<ChartTooltip />} />
          {priceDataStartDate && chartData.some(d => d.date < priceDataStartDate) && (
            <ReferenceLine
              x={priceDataStartDate}
              stroke="var(--warning, #eab308)"
              strokeDasharray="5 5"
              strokeWidth={1.5}
              label={{ value: "Limited price data", position: "top", fill: "var(--warning, #eab308)", fontSize: 10 }}
            />
          )}
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--accent)"
            strokeWidth={2}
            fill="url(#chartGradient)"
            dot={false}
            activeDot={{ r: 4, fill: "var(--accent)" }}
          />
          <Line
            type="monotone"
            dataKey="costBasis"
            stroke="var(--warning, #eab308)"
            strokeWidth={1.5}
            strokeDasharray="4 3"
            dot={false}
            activeDot={{ r: 3, fill: "var(--warning, #eab308)" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
