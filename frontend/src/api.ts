import type { ApprovalItem, CostAnomaly, DeciderResponseTrace, BedrockReport, HealthInfo, Scenario } from "./types";

const API_BASE = "http://127.0.0.1:8000";

export async function fetchHealth(): Promise<HealthInfo> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function fetchScenarios(): Promise<Scenario[]> {
  const res = await fetch(`${API_BASE}/api/demo/scenarios`);
  if (!res.ok) throw new Error(`Failed to load scenarios: ${res.statusText}`);
  return res.json();
}

export async function runAnalysis(
  scenarioId: string = "compute_spike",
  useAwsCostExplorer: boolean = false
): Promise<{
  anomaly: CostAnomaly;
  decision: DeciderResponseTrace;
  report: BedrockReport;
  approval: ApprovalItem | null;
  is_simulated: boolean;
}> {
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scenario_id: scenarioId,
      use_aws_cost_explorer: useAwsCostExplorer,
    }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Analysis failed: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchDecisions(): Promise<DeciderResponseTrace[]> {
  const res = await fetch(`${API_BASE}/api/decisions?limit=15`);
  if (!res.ok) throw new Error(`Failed to load decisions: ${res.statusText}`);
  return res.json();
}

export async function fetchApprovals(): Promise<ApprovalItem[]> {
  const res = await fetch(`${API_BASE}/api/approvals`);
  if (!res.ok) throw new Error(`Failed to load approvals: ${res.statusText}`);
  return res.json();
}

export async function submitApprovalDecision(
  approvalId: string,
  action: "approved" | "rejected",
  notes: string = "Reviewed in CloudCost Sentinel dashboard."
): Promise<ApprovalItem> {
  const res = await fetch(`${API_BASE}/api/approvals/${approvalId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action,
      reviewed_by: "lead-cloud-engineer@company.internal",
      notes,
    }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Approval decision failed: ${res.statusText}`);
  }
  return res.json();
}
