import type { ApprovalItem, CostAnomaly, DeciderResponseTrace, BedrockReport, HealthInfo, Scenario } from "./types";

// VITE_API_BASE_URL is the backend origin only, with no /api suffix.
export const getApiBase = (): string => {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl !== undefined && envUrl !== "") {
    try {
      const parsed = new URL(envUrl.trim());
      if (!/^https?:$/.test(parsed.protocol) || parsed.pathname !== "/" || parsed.search || parsed.hash) {
        throw new Error();
      }
      return parsed.origin;
    } catch {
      throw new Error("VITE_API_BASE_URL must be an HTTP(S) backend origin without a path, query, or fragment.");
    }
  }
  // In development, default to local FastAPI dev server
  if (import.meta.env.DEV) {
    return "http://127.0.0.1:8000";
  }
  throw new Error("Backend URL is not configured. Set VITE_API_BASE_URL to your API origin and redeploy the frontend.");
};

function apiUrl(path: string): string {
  return `${getApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
}

async function requestJson<T>(path: string, init: RequestInit = {}, operation = "API request"): Promise<T> {
  const url = apiUrl(path);
  let response: Response;
  try {
    const headers = new Headers(init.headers);
    response = await fetch(url, { ...init, headers });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("Cannot reach the backend. Check its availability and VITE_API_BASE_URL, then retry.");
  }

  const body = await response.text();
  let payload: unknown;
  try {
    payload = body ? JSON.parse(body) : undefined;
  } catch {
    payload = undefined;
  }
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload
      ? String((payload as { detail: unknown }).detail)
      : undefined;
    throw new Error(detail || (body && !payload
      ? `${operation} returned an unexpected non-JSON response (${response.status}). Check the backend URL.`
      : `${operation} failed (${response.status}${response.statusText ? ` ${response.statusText}` : ""}).`));
  }
  if (!payload) throw new Error(`${operation} returned an empty or invalid JSON response.`);
  return payload as T;
}

export async function fetchHealth(): Promise<HealthInfo> {
  return requestJson<HealthInfo>("/api/health", {}, "Health check");
}

export async function fetchScenarios(): Promise<Scenario[]> {
  return requestJson<Scenario[]>("/api/demo/scenarios", {}, "Loading scenarios");
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
  return requestJson<{
    anomaly: CostAnomaly;
    decision: DeciderResponseTrace;
    report: BedrockReport;
    approval: ApprovalItem | null;
    is_simulated: boolean;
  }>("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({
      scenario_id: scenarioId,
      use_aws_cost_explorer: useAwsCostExplorer,
    }),
  }, "Analysis");
}

export async function fetchDecisions(): Promise<DeciderResponseTrace[]> {
  return requestJson<DeciderResponseTrace[]>("/api/decisions?limit=15", {}, "Loading decisions");
}

export async function fetchApprovals(): Promise<ApprovalItem[]> {
  return requestJson<ApprovalItem[]>("/api/approvals", {}, "Loading approvals");
}

export async function submitApprovalDecision(
  approvalId: string,
  action: "approved" | "rejected",
  notes: string = "Reviewed in CloudCost Sentinel dashboard."
): Promise<ApprovalItem> {
  return requestJson<ApprovalItem>(`/api/approvals/${encodeURIComponent(approvalId)}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action,
      notes,
    }),
  }, "Recording approval");
}
