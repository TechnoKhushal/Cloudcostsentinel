import type { ApprovalItem, CostAnomaly, DeciderResponseTrace, BedrockReport, HealthInfo, Scenario } from "./types";

export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

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

function formatValidationDetail(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return undefined;
  const issues = detail.flatMap((issue: unknown) => {
    if (!issue || typeof issue !== "object") return [];
    const item = issue as { loc?: unknown[]; msg?: unknown };
    if (typeof item.msg !== "string") return [];
    const location = Array.isArray(item.loc) ? item.loc.map(String).join(".") : "request";
    return [`${location}: ${item.msg}`];
  });
  return issues.length ? `Validation failed: ${issues.join("; ")}` : undefined;
}

async function requestJson<T>(path: string, init: RequestInit = {}, operation = "API request"): Promise<T> {
  const url = apiUrl(path);
  const timeout = AbortSignal.timeout(20_000);
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
  let response: Response;
  try {
    const headers = new Headers(init.headers);
    response = await fetch(url, { ...init, headers, signal });
  } catch (error) {
    if (init.signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) throw error;
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError("Backend request timed out. The service may be starting; retry in a few seconds.");
    }
    throw new ApiError("Cannot reach the backend. Check network access, the backend CORS origin allowlist, and VITE_API_BASE_URL; retry if the service is waking.");
  }

  const body = await response.text();
  let payload: unknown;
  try {
    payload = body ? JSON.parse(body) : undefined;
  } catch {
    payload = undefined;
  }
  if (!response.ok) {
    const rawDetail = payload && typeof payload === "object" && "detail" in payload
      ? (payload as { detail: unknown }).detail
      : undefined;
    const detail = response.status === 422 ? formatValidationDetail(rawDetail) : typeof rawDetail === "string" ? rawDetail : undefined;
    const statusMessage = response.status === 401 ? "Authentication required. Sign in with the configured identity provider."
      : response.status === 403 ? "This account is not allowed to perform this action. Check its permissions or role."
      : response.status === 404 ? `Backend endpoint ${path} was not found. Check VITE_API_BASE_URL and the API version.`
      : response.status === 422 ? undefined
      : response.status >= 500 ? "The backend failed while handling this request. Retry or contact the service operator."
      : undefined;
    const message = statusMessage || detail || (body && !payload
      ? `${operation} returned an unexpected non-JSON response (${response.status}). Check the backend URL.`
      : `${operation} failed (${response.status}${response.statusText ? ` ${response.statusText}` : ""}).`);
    throw new ApiError(message, response.status);
  }
  if (!payload) throw new ApiError(`${operation} returned an empty or invalid JSON response.`, response.status);
  return payload as T;
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthInfo> {
  return requestJson<HealthInfo>("/api/health", { signal }, "Health check");
}

export async function fetchScenarios(signal?: AbortSignal): Promise<Scenario[]> {
  return requestJson<Scenario[]>("/api/demo/scenarios", { signal }, "Loading scenarios");
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
  cost_data_source: string;
  partial_data: boolean;
  data_warnings: string[];
}> {
  return requestJson<{
    anomaly: CostAnomaly;
    decision: DeciderResponseTrace;
    report: BedrockReport;
    approval: ApprovalItem | null;
    is_simulated: boolean;
    cost_data_source: string;
    partial_data: boolean;
    data_warnings: string[];
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

export async function fetchApprovals(signal?: AbortSignal): Promise<ApprovalItem[]> {
  return requestJson<ApprovalItem[]>("/api/approvals", { signal }, "Loading approvals");
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
