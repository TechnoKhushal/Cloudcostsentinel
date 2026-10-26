import assert from "node:assert/strict";
import { test } from "node:test";
import { buildAnalysisCsv, buildExecutiveBrief } from "../src/analysisExport.ts";
import type { BedrockReport, CostAnomaly, DeciderResponseTrace } from "../src/types.ts";

const anomaly = {
  anomaly_id: "anomaly-1",
  scenario_id: "compute_spike",
  scenario_name: "Compute spike",
  service: "Amazon EC2",
  environment: "production",
  owner: "platform",
  criticality: "high",
  metrics: {
    current_spend: 1200,
    baseline_spend: 500,
    delta_amount: 700,
    delta_percentage: 140,
    persistence_days: 2,
    monthly_budget: 12000,
    month_to_date_spend: 6000,
    budget_burn_percentage: 50,
    forecast_month_end: 18000,
    uncertainty_flag: false,
    anomaly_detected: true,
  },
  time_series: [],
  currency: "USD",
  detected_at: "2026-10-26T00:00:00Z",
  is_simulated: true,
} as CostAnomaly;

const decision = {
  decision_id: "decision-1",
  timestamp: "2026-10-26T00:00:00Z",
  action: "request_approval",
  confidence: 0.84,
  probabilities: {},
  latency_ms: 2,
  model_id: "demo",
  provider: "mock-simulated",
  is_fallback: false,
  question: { type: "choice", instructions: "Choose", criteria: {} },
  normalized_state: "spend spike",
  executed_action: "CREATE_APPROVAL_REVIEW_ITEM",
  executed_details: {},
} as DeciderResponseTrace;

const report = {
  report_id: "report-1",
  anomaly_id: anomaly.anomaly_id,
  decision_id: decision.decision_id,
  title: "Compute spike review",
  executive_summary: "Daily spend rose above the baseline.",
  observed_facts: ["Spend rose by $700 per day."],
  decider_action_audit: "request_approval",
  likely_investigation_areas: [],
  safe_recommendations: ["Review recent scaling events."],
  assumptions_and_limitations: [],
  follow_up_checklist: [],
  provider: "demo-narrative-adapter",
  model_id: "template",
  is_simulated: true,
  generated_at: "2026-10-26T00:00:00Z",
} as BedrockReport;

test("analysis export includes spend, budget, decision, and report evidence", () => {
  const csv = buildAnalysisCsv(anomaly, decision, report);
  assert.match(csv, /"Observed daily spend","1200"/);
  assert.match(csv, /"Forecast month end","18000"/);
  assert.match(csv, /"Recommendation","request_approval"/);
  assert.match(csv, /"Observed fact","Fact 1","Spend rose by \$700 per day\."/);
  assert.match(csv, /"Recommendation","Recommendation 1","Review recent scaling events\."/);
});

test("analysis CSV quotes cells and neutralizes spreadsheet formulas", () => {
  const unsafe = { ...report, executive_summary: '  =HYPERLINK("https://example.invalid","open")' };
  const csv = buildAnalysisCsv(anomaly, decision, unsafe);
  assert.match(csv, /"Report","Executive summary","'  =HYPERLINK\(""https:\/\/example\.invalid"",""open""\)"/);
});

test("executive brief summarizes the recommendation and safety boundary", () => {
  const brief = buildExecutiveBrief(anomaly, decision, report);
  assert.match(brief, /Compute spike/);
  assert.match(brief, /\+USD 700\/day/);
  assert.match(brief, /request approval \(84\.0% confidence\)/);
  assert.match(brief, /no cloud resources were changed/i);
});
