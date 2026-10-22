import type { ApprovalItem, CostAnomaly, DeciderResponseTrace, BedrockReport, HealthInfo, Scenario } from "./types";

// Configurable API base URL; in production builds falls back to same-origin (/api) if VITE_API_BASE_URL is not set
const getApiBase = (): string => {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl !== undefined && envUrl !== "") {
    return envUrl.replace(/\/+$/, "");
  }
  // In development, default to local FastAPI dev server
  if (import.meta.env.DEV) {
    return "http://127.0.0.1:8000";
  }
  return "";
};

const API_BASE = getApiBase();

function getAuthHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const token = localStorage.getItem("sentinel_token");
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export async function fetchHealth(): Promise<HealthInfo> {
  const res = await fetch(`${API_BASE}/api/health`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function fetchScenarios(): Promise<Scenario[]> {
  const res = await fetch(`${API_BASE}/api/demo/scenarios`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load scenarios: ${res.statusText}`);
  return res.json();
}

export async function runAnalysis(
  scenarioId: string = "compute_spike",
  useAwsCostExplorer: boolean = false,
  signal?: AbortSignal
): Promise<{
  anomaly: CostAnomaly;
  decision: DeciderResponseTrace;
  report: BedrockReport;
  approval: ApprovalItem | null;
  is_simulated: boolean;
}> {
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: getAuthHeaders(),
    signal,
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
  const res = await fetch(`${API_BASE}/api/decisions?limit=15`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load decisions: ${res.statusText}`);
  return res.json();
}

export async function fetchApprovals(): Promise<ApprovalItem[]> {
  const res = await fetch(`${API_BASE}/api/approvals`, {
    headers: getAuthHeaders(),
  });
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
    headers: getAuthHeaders(),
    body: JSON.stringify({
      action,
      notes,
    }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Approval decision failed: ${res.statusText}`);
  }
  return res.json();
}
