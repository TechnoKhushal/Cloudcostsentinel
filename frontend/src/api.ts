import type { ApprovalItem, CostAnomaly, DeciderResponseTrace, InvestigationReport, HealthInfo, Scenario } from "./types";

export class ApiError extends Error {
  readonly status?: number;
  readonly endpoint: string;
  readonly requestId?: string;

  constructor(message: string, options: { status?: number; endpoint: string; requestId?: string }) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.endpoint = options.endpoint;
    this.requestId = options.requestId;
  }
}

// VITE_API_BASE_URL is the backend origin only, without an /api suffix.
export interface BuildEnvironment { VITE_API_BASE_URL?: string; DEV?: boolean }

export const resolveApiBase = (environment: BuildEnvironment | undefined): string => {
  const envUrl = environment?.VITE_API_BASE_URL;
  if (envUrl !== undefined && envUrl.trim() !== "") {
    try {
      const parsed = new URL(envUrl.trim());
      if (!/^https?:$/.test(parsed.protocol) || parsed.pathname !== "/" || parsed.search || parsed.hash) throw new Error();
      return parsed.origin;
    } catch {
      throw new Error("VITE_API_BASE_URL must be an HTTP(S) backend origin without a path, query, or fragment.");
    }
  }
  if (environment?.DEV) return "http://127.0.0.1:8000";
  throw new Error("Backend URL is not configured. Set VITE_API_BASE_URL to the Render API origin and redeploy the frontend.");
};

export const getApiBase = (): string => resolveApiBase(import.meta.env);

export function apiUrl(path: string, environment: BuildEnvironment | undefined = import.meta.env): string {
  const base = resolveApiBase(environment);
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}
function readableDetail(detail: unknown): string | undefined {
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

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export async function requestJson<T>(path: string, init: RequestInit = {}, operation = "API request", environment: BuildEnvironment | undefined = import.meta.env): Promise<T> {
  const url = apiUrl(path, environment);
  const endpoint = new URL(url).pathname;
  const timeout = AbortSignal.timeout(20_000);
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers, signal });
  } catch (error) {
    if (init.signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) throw error;
    const isTimeout = error instanceof DOMException && error.name === "TimeoutError";
    throw new ApiError(
      isTimeout
        ? "Backend request timed out. The service may be starting; retry in a few seconds."
        : "Cannot reach the backend. Check network access, the backend CORS allowlist, and VITE_API_BASE_URL; retry if the service is waking.",
      { endpoint },
    );
  }

  const requestId = response.headers.get("x-request-id") ?? response.headers.get("x-correlation-id") ?? undefined;
  const body = await response.text();
  let payload: unknown;
  try {
    payload = body ? JSON.parse(body) : undefined;
  } catch {
    payload = undefined;
  }
  if (!response.ok) {
    const rawDetail = isObject(payload) ? payload.detail : undefined;
    const detail = response.status === 422 ? readableDetail(rawDetail) : typeof rawDetail === "string" ? rawDetail : undefined;
    const statusMessage = response.status === 401 ? "Authentication required. Sign in with the configured identity provider."
      : response.status === 403 ? "This account is not allowed to perform this action. Check its permissions or role."
      : response.status === 404 ? `Backend endpoint ${endpoint} was not found. Check the API deployment.`
      : response.status === 409 ? "This item changed since it was loaded. Refresh the dashboard and try again."
      : response.status === 429 ? "The service is receiving too many requests. Wait briefly, then retry."
      : response.status === 422 ? undefined
      : response.status >= 500 ? "The backend failed while handling this request. Retry or contact the service operator."
      : undefined;
    const message = statusMessage || detail || (payload === undefined
      ? `${operation} returned an unexpected response (${response.status}). Check the backend URL.`
      : `${operation} failed (${response.status}${response.statusText ? ` ${response.statusText}` : ""}).`);
    throw new ApiError(message, { status: response.status, endpoint, requestId });
  }
  if (payload === undefined) throw new ApiError(`${operation} returned an empty or invalid JSON response.`, { status: response.status, endpoint, requestId });
  return payload as T;
}

function expectArray<T>(value: unknown, endpoint: string, isItem: (item: unknown) => item is T): T[] {
  if (!Array.isArray(value) || !value.every(isItem)) {
    throw new ApiError(`The backend returned an unexpected response for ${endpoint}. Refresh or contact the service operator.`, { endpoint });
  }
  return value;
}

const isScenario = (item: unknown): item is Scenario => isObject(item)
  && ["id", "name", "description", "expected_response", "service", "environment"].every((key) => typeof item[key] === "string");
const isApproval = (item: unknown): item is ApprovalItem => isObject(item)
  && typeof item.id === "string" && ["pending", "approved", "rejected"].includes(String(item.status))
  && typeof item.service === "string" && typeof item.environment === "string"
  && typeof item.suggested_action === "string" && typeof item.estimated_monthly_savings === "number";
const isDecision = (item: unknown): item is DeciderResponseTrace => isObject(item)
  && typeof item.decision_id === "string" && ["monitor", "notify_owner", "request_approval"].includes(String(item.action))
  && typeof item.timestamp === "string" && typeof item.provider === "string";
export async function fetchHealth(signal?: AbortSignal, environment: BuildEnvironment | undefined = import.meta.env): Promise<HealthInfo> {
  const value: unknown = await requestJson("/api/health", { signal }, "Health check", environment);
  if (!isObject(value) || typeof value.environment !== "string" || !isObject(value.providers)
    || !isObject(value.providers.decider) || !isObject(value.providers.narrator) || !isObject(value.providers.cost_explorer)) {
    throw new ApiError("The health endpoint returned an unexpected response shape.", { endpoint: "/api/health" });
  }
  return value as unknown as HealthInfo;
}

export async function fetchScenarios(signal?: AbortSignal, environment: BuildEnvironment | undefined = import.meta.env): Promise<Scenario[]> {
  const value: unknown = await requestJson("/api/demo/scenarios", { signal }, "Loading scenarios", environment);
  return expectArray(value, "/api/demo/scenarios", isScenario);
}

export interface AnalysisResult {
  anomaly: CostAnomaly;
  decision: DeciderResponseTrace;
  report: InvestigationReport;
  approval: ApprovalItem | null;
  is_simulated: boolean;
  cost_data_source: string;
  partial_data: boolean;
  data_warnings: string[];
}

export async function runAnalysis(
  scenarioId = "compute_spike",
  useAwsCostExplorer = false,
  signal?: AbortSignal,
  environment: BuildEnvironment | undefined = import.meta.env,
): Promise<AnalysisResult> {
  const value: unknown = await requestJson("/api/analyze", {
    method: "POST",
    signal,
    body: JSON.stringify({ scenario_id: scenarioId, use_aws_cost_explorer: useAwsCostExplorer }),
  }, "Analysis", environment);
  if (!isObject(value) || !isObject(value.anomaly) || !isObject(value.anomaly.metrics) || !Array.isArray(value.anomaly.time_series)
    || !isObject(value.decision) || !isObject(value.report) || !Array.isArray(value.report.observed_facts)
    || !Array.isArray(value.report.safe_recommendations) || typeof value.is_simulated !== "boolean"
    || typeof value.cost_data_source !== "string" || typeof value.partial_data !== "boolean" || !Array.isArray(value.data_warnings)) {
    throw new ApiError("The analysis endpoint returned an unexpected response shape.", { endpoint: "/api/analyze" });
  }
  return value as unknown as AnalysisResult;
}

export async function fetchDecisions(signal?: AbortSignal, environment: BuildEnvironment | undefined = import.meta.env): Promise<DeciderResponseTrace[]> {
  const value: unknown = await requestJson("/api/decisions?limit=15", { signal }, "Loading decisions", environment);
  return expectArray(value, "/api/decisions", isDecision);
}

export async function fetchApprovals(signal?: AbortSignal, environment: BuildEnvironment | undefined = import.meta.env): Promise<ApprovalItem[]> {
  const value: unknown = await requestJson("/api/approvals", { signal }, "Loading approvals", environment);
  return expectArray(value, "/api/approvals", isApproval);
}

export async function submitApprovalDecision(
  approvalId: string,
  action: "approved" | "rejected",
  notes = "Reviewed in CloudCost Sentinel dashboard.",
  signal?: AbortSignal,
  environment: BuildEnvironment | undefined = import.meta.env,
): Promise<ApprovalItem> {
  const value: unknown = await requestJson(`/api/approvals/${encodeURIComponent(approvalId)}/decision`, {
    method: "POST",
    signal,
    body: JSON.stringify({ action, notes }),
  }, "Recording approval", environment);
  if (!isApproval(value)) throw new ApiError("The approval endpoint returned an unexpected response shape.", { endpoint: "/api/approvals/{approval_id}/decision" });
  return value;
}
