import React from "react";
import { DollarSign, TrendingUp, AlertTriangle, Calendar, Target } from "lucide-react";
import type { SpendMetrics } from "../types";

interface OverviewCardsProps {
  metrics: SpendMetrics | null;
  service: string;
  environment: string;
}

export const OverviewCards: React.FC<OverviewCardsProps> = ({ metrics, service, environment }) => {
  if (!metrics) return null;

  const isSpike = metrics.delta_percentage > 20.0;
  const isBudgetWarning = metrics.budget_burn_percentage > 90.0;

  return (
    <div className="metrics-grid">
      {/* Current Spend */}
      <div className="metric-card">
        <div className="metric-label">
          <span>Observed Daily Spend</span>
          <DollarSign size={16} />
        </div>
        <div className="metric-value">${metrics.current_spend.toLocaleString("en-US", { minimumFractionDigits: 2 })}</div>
        <div className={`metric-sub ${isSpike ? "danger" : "success"}`}>
          <TrendingUp size={14} />
          {metrics.delta_percentage > 0 ? `+${metrics.delta_percentage}%` : `${metrics.delta_percentage}%`} vs baseline
        </div>
      </div>

      {/* Expected Baseline */}
      <div className="metric-card">
        <div className="metric-label">
          <span>Baseline Rolling Mean</span>
          <Target size={16} />
        </div>
        <div className="metric-value">${metrics.baseline_spend.toLocaleString("en-US", { minimumFractionDigits: 2 })}</div>
        <div className="metric-sub">
          7-day historical reference for {service} ({environment})
        </div>
      </div>

      {/* Persistence & Delta */}
      <div className="metric-card">
        <div className="metric-label">
          <span>Anomaly Persistence</span>
          <Calendar size={16} />
        </div>
        <div className="metric-value">{metrics.persistence_days} {metrics.persistence_days === 1 ? "day" : "days"}</div>
        <div className={`metric-sub ${metrics.persistence_days >= 2 ? "warning" : ""}`}>
          <AlertTriangle size={14} />
          +${metrics.delta_amount.toFixed(2)} / day excess burn
        </div>
      </div>

      {/* Budget Burn & Forecast */}
      <div className="metric-card">
        <div className="metric-label">
          <span>Forecast vs Budget</span>
          <DollarSign size={16} />
        </div>
        <div className="metric-value">{metrics.budget_burn_percentage.toFixed(1)}%</div>
        <div className={`metric-sub ${isBudgetWarning ? "danger" : "success"}`}>
          Proj: ${metrics.forecast_month_end.toLocaleString()} of ${metrics.monthly_budget.toLocaleString()}
        </div>
      </div>
    </div>
  );
};
