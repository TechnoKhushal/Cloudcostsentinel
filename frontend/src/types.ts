export interface CostDataPoint {
  date: string;
  spend: number;
  baseline: number;
  is_anomaly: boolean;
  service: string;
  environment: string;
}

export interface SpendMetrics {
  current_spend: number;
  baseline_spend: number;
  delta_amount: number;
  delta_percentage: number;
  persistence_days: number;
  monthly_budget: number;
  month_to_date_spend: number;
  budget_burn_percentage: number;
  forecast_month_end: number;
  uncertainty_flag: boolean;
  anomaly_detected: boolean;
}

export interface CostAnomaly {
  anomaly_id: string;
  scenario_id: string;
  scenario_name: string;
  service: string;
  environment: string;
  owner: string;
  criticality: "low" | "medium" | "high" | "critical";
  metrics: SpendMetrics;
  time_series: CostDataPoint[];
  currency: string;
  detected_at: string;
  is_simulated: boolean;
}

export interface DeciderQuestionSpec {
  type: string;
  instructions: string;
  criteria: Record<string, string>;
}

export interface DeciderResponseTrace {
  decision_id: string;
  timestamp: string;
  action: "monitor" | "notify_owner" | "request_approval";
  confidence: number;
  probabilities: Record<string, number>;
  latency_ms: number;
  model_id: string;
  provider: string;
  is_fallback: boolean;
  fallback_reason?: string | null;
  question: DeciderQuestionSpec;
  normalized_state: string;
  executed_action: string;
  executed_details: Record<string, any>;
}

export interface InvestigationReport {
  report_id: string;
  anomaly_id: string;
  decision_id: string;
  title: string;
  executive_summary: string;
  observed_facts: string[];
  decider_action_audit: string;
  likely_investigation_areas: string[];
  safe_recommendations: string[];
  assumptions_and_limitations: string[];
  follow_up_checklist: string[];
  provider: string;
  model_id: string;
  is_simulated: boolean;
  generated_at: string;
}
/** @deprecated Compatibility alias; reports are provider-neutral. */
export type BedrockReport = InvestigationReport;

export interface ApprovalItem {
  id: string;
  decision_id: string;
  anomaly_id: string;
  service: string;
  environment: string;
  suggested_action: string;
  estimated_monthly_savings: number;
  status: "pending" | "approved" | "rejected";
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  notes?: string | null;
  created_at: string;
  is_simulated: boolean;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  expected_response: string;
  service: string;
  environment: string;
}

export interface HealthInfo {
  status: string;
  service: string;
  version: string;
  environment: string;
  auth?: {
    enabled: boolean;
    mode: string;
    warning?: string | null;
  };
  providers: {
    decider: {
      provider: string;
      state: string;
      model_id: string;
      min_confidence_threshold: number;
      endpoint: string;
      ready?: boolean;
    };
    narrator: {
      provider: string;
      state: string;
      model_id: string;
      ready?: boolean;
    };
    cost_explorer: {
      enabled: boolean;
      status: string;
      message: string;
      region?: string;
    };
    notifications?: {
      provider: string;
      state: string;
    };
  };
  safety_guarantee: string;
}
