import type { InvestigationReport, CostAnomaly, DeciderResponseTrace } from "./types";

function safeCsvCell(value: unknown): string {
  let text = value == null ? "" : String(value);
  if (/^[=+@-]/.test(text.trimStart())) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function buildAnalysisCsv(anomaly: CostAnomaly, decision: DeciderResponseTrace, report: InvestigationReport): string {
  const rows: [string, string, unknown][] = [
    ["Analysis", "Scenario", anomaly.scenario_name],
    ["Analysis", "Scenario ID", anomaly.scenario_id],
    ["Analysis", "Service", anomaly.service],
    ["Analysis", "Environment", anomaly.environment],
    ["Analysis", "Owner", anomaly.owner],
    ["Analysis", "Criticality", anomaly.criticality],
    ["Analysis", "Currency", anomaly.currency],
    ["Analysis", "Detected at", anomaly.detected_at],
    ["Spend", "Observed daily spend", anomaly.metrics.current_spend],
    ["Spend", "Baseline daily spend", anomaly.metrics.baseline_spend],
    ["Spend", "Daily delta", anomaly.metrics.delta_amount],
    ["Spend", "Delta percentage", anomaly.metrics.delta_percentage],
    ["Spend", "Persistence days", anomaly.metrics.persistence_days],
    ["Budget", "Monthly budget", anomaly.metrics.monthly_budget],
    ["Budget", "Month-to-date spend", anomaly.metrics.month_to_date_spend],
    ["Budget", "Forecast month end", anomaly.metrics.forecast_month_end],
    ["Budget", "Budget burn percentage", anomaly.metrics.budget_burn_percentage],
    ["Decision", "Recommendation", decision.action],
    ["Decision", "Confidence", decision.confidence],
    ["Decision", "Provider", decision.provider],
    ["Decision", "Fallback used", decision.is_fallback],
    ["Report", "Title", report.title],
    ["Report", "Executive summary", report.executive_summary],
    ...report.observed_facts.map((fact, index): [string, string, unknown] => ["Observed fact", `Fact ${index + 1}`, fact]),
    ...report.safe_recommendations.map((recommendation, index): [string, string, unknown] => ["Recommendation", `Recommendation ${index + 1}`, recommendation]),
  ];

  return [
    ["Section", "Field", "Value"].map(safeCsvCell).join(","),
    ...rows.map((row) => row.map(safeCsvCell).join(",")),
  ].join("\r\n");
}

export function buildExecutiveBrief(anomaly: CostAnomaly, decision: DeciderResponseTrace, report: InvestigationReport): string {
  const dailyDelta = `${anomaly.metrics.delta_amount >= 0 ? "+" : ""}${anomaly.currency} ${anomaly.metrics.delta_amount.toLocaleString("en-US", { maximumFractionDigits: 2 })}/day`;
  const confidence = `${(decision.confidence * 100).toFixed(1)}%`;
  return [
    `CloudCost Sentinel analysis: ${anomaly.scenario_name}`,
    `${anomaly.service} · ${anomaly.environment} · ${anomaly.criticality} criticality`,
    `Daily spend: ${anomaly.currency} ${anomaly.metrics.current_spend.toLocaleString("en-US", { maximumFractionDigits: 2 })} (${dailyDelta} vs. baseline).`,
    `Forecast: ${anomaly.metrics.budget_burn_percentage.toFixed(1)}% of the ${anomaly.currency} ${anomaly.metrics.monthly_budget.toLocaleString("en-US", { maximumFractionDigits: 2 })} monthly budget.`,
    `Recommendation: ${decision.action.replaceAll("_", " ")} (${confidence} confidence${decision.is_fallback ? "; safety fallback" : ""}).`,
    report.executive_summary,
    "Decision support only. Review before taking action; no cloud resources were changed.",
  ].join("\n");
}

export function downloadAnalysisCsv(csv: string, scenarioId: string): void {
  const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const safeScenario = scenarioId.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-|-$/g, "") || "analysis";
  link.href = url;
  link.download = `cloudcost-sentinel-${safeScenario}.csv`;
  link.style.display = "none";
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
