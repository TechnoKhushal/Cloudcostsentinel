import React from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { CostDataPoint } from "../types";

interface SpendChartProps {
  data: CostDataPoint[];
  baseline: number;
  service: string;
}

export const SpendChart: React.FC<SpendChartProps> = ({ data, baseline, service }) => {
  const thresholdVal = baseline * 1.25;

  return (
    <div className="panel-card" style={{ height: "360px", display: "flex", flexDirection: "column" }}>
      <div className="panel-header">
        <h2 className="panel-title">
          <span>Spend Telemetry & Anomaly Trajectory</span>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>({service})</span>
        </h2>
        <div style={{ display: "flex", gap: "1rem", fontSize: "0.75rem" }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span style={{ width: 10, height: 10, background: "#06b6d4", borderRadius: 2 }} />
            Observed Spend
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span style={{ width: 10, height: 2, background: "#94a3b8" }} />
            Baseline (${baseline.toFixed(0)})
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span style={{ width: 10, height: 2, background: "#f43f5e" }} />
            Threshold (+25%)
          </span>
        </div>
      </div>

      <div style={{ flex: 1, width: "100%", minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="spendGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2b48" vertical={false} />
            <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickLine={false} />
            <YAxis
              stroke="#64748b"
              fontSize={11}
              tickLine={false}
              tickFormatter={(val) => `$${val}`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#0e1320",
                borderColor: "#2e3e67",
                borderRadius: "8px",
                fontSize: "12px",
                color: "#f1f5f9",
              }}
              formatter={(val: any) => [`$${Number(val).toFixed(2)}`, "Daily Spend"]}
            />
            <ReferenceLine y={baseline} stroke="#94a3b8" strokeDasharray="3 3" />
            <ReferenceLine y={thresholdVal} stroke="#f43f5e" strokeDasharray="4 4" />
            <Area
              type="monotone"
              dataKey="spend"
              stroke="#06b6d4"
              strokeWidth={2.5}
              fillOpacity={1}
              fill="url(#spendGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
