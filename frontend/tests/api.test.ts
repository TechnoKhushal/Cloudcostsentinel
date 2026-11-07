import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { ApiError, apiUrl, connectAwsIntegration, disconnectAwsIntegration, fetchAccountProfile, fetchApprovals, fetchAwsIntegration, fetchDecisions, fetchHealth, fetchLatestAnalysis, fetchScenarios, requestJson, resolveApiBase, runAnalysis, submitApprovalDecision, updateAccountProfile, verifyAwsIntegration } from "../src/api.ts";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
const production = { VITE_API_BASE_URL: "https://cloudcostsentinel.onrender.com/", DEV: false };

test("API base requires a production origin and normalizes the trailing slash", () => {
  assert.equal(resolveApiBase(production), "https://cloudcostsentinel.onrender.com");
  assert.equal(resolveApiBase({ DEV: true }), "http://127.0.0.1:8000");
  assert.throws(() => resolveApiBase({ DEV: false }), /VITE_API_BASE_URL/);
  assert.throws(() => resolveApiBase({ VITE_API_BASE_URL: "https://api.example.com/api" }), /backend origin/);
});

test("API URL appends each route once to the backend origin", () => {
  assert.equal(apiUrl("/api/health", production), "https://cloudcostsentinel.onrender.com/api/health");
  assert.equal(apiUrl("api/approvals", production), "https://cloudcostsentinel.onrender.com/api/approvals");
});

test("GET sends Accept without an unnecessary JSON Content-Type", async () => {
  globalThis.fetch = async (input, init) => {
    assert.equal(String(input), "https://cloudcostsentinel.onrender.com/api/health");
    const headers = new Headers(init?.headers);
    assert.equal(headers.get("Accept"), "application/json");
    assert.equal(headers.has("Content-Type"), false);
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  assert.deepEqual(await requestJson("/api/health", {}, "Health", production), { ok: true });
});

test("JSON body requests set Content-Type and preserve the HTTP method", async () => {
  globalThis.fetch = async (input, init) => {
    assert.equal(String(input), "https://cloudcostsentinel.onrender.com/api/approvals/a/decision");
    assert.equal(init?.method, "POST");
    assert.equal(new Headers(init?.headers).get("Content-Type"), "application/json");
    assert.equal(init?.body, JSON.stringify({ action: "approved" }));
    return new Response(JSON.stringify({ saved: true }), { status: 200 });
  };
  await requestJson("/api/approvals/a/decision", { method: "POST", body: JSON.stringify({ action: "approved" }) }, "Save", production);
});

for (const [status, expected] of [
  [401, /Authentication required/], [403, /not allowed/], [404, /endpoint .* was not found/],
  [409, /changed since it was loaded/], [422, /scenario is invalid/], [429, /too many requests/],
  [500, /backend failed/],
] as const) {
  test(`HTTP ${status} becomes a safe typed API error`, async () => {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: status === 422 ? "scenario is invalid" : "internal traceback secret" }), {
      status, headers: { "x-request-id": "req-safe-123" },
    });
    await assert.rejects(requestJson("/api/analyze", {}, "Analysis", production), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, status);
      assert.equal(error.endpoint, "/api/analyze");
      assert.equal(error.requestId, "req-safe-123");
      assert.match(error.message, expected);
      if (status >= 500) assert.doesNotMatch(error.message, /traceback secret/);
      return true;
    });
  });
}

test("network failures and non-JSON HTTP errors stay human-readable", async () => {
  globalThis.fetch = async () => { throw new TypeError("network details"); };
  await assert.rejects(requestJson("/api/health", {}, "Health", production), /Cannot reach the backend/);
  globalThis.fetch = async () => new Response("<html>proxy error</html>", { status: 502 });
  await assert.rejects(requestJson("/api/health", {}, "Health", production), /backend failed/);
});

test("caller cancellation remains cancellation, not a visible backend error", async () => {
  const controller = new AbortController();
  controller.abort();
  globalThis.fetch = async () => { throw new DOMException("Aborted", "AbortError"); };
  await assert.rejects(requestJson("/api/analyze", { signal: controller.signal }, "Analysis", production), (error: unknown) => error instanceof DOMException && error.name === "AbortError");
});


test("each dashboard API helper uses the current FastAPI route and intended method", async () => {
  const calls: Array<{ path: string; method: string; headers: Headers; body: BodyInit | null | undefined }> = [];
  const approval = { id: "appr-1", decision_id: "dec-1", anomaly_id: "anom-1", service: "compute", environment: "demo", suggested_action: "review", estimated_monthly_savings: 100, status: "approved", created_at: "2026-01-01T00:00:00Z", is_simulated: true };
  globalThis.fetch = async (input, init) => {
    const url = new URL(String(input));
    calls.push({ path: `${url.pathname}${url.search}`, method: init?.method ?? "GET", headers: new Headers(init?.headers), body: init?.body });
    let payload: unknown = [];
    if (url.pathname === "/api/health") payload = { environment: "demo", providers: { decider: {}, narrator: {}, cost_explorer: {} } };
    if (url.pathname === "/api/analyze") payload = { anomaly: { metrics: {}, time_series: [] }, decision: {}, report: { observed_facts: [], safe_recommendations: [] }, is_simulated: true, cost_data_source: "synthetic_scenario", partial_data: false, data_warnings: [] };
    if (url.pathname === "/api/analysis/latest") payload = null;
    if (url.pathname === "/api/approvals/appr-1/decision") payload = approval;
    return new Response(JSON.stringify(payload), { status: 200 });
  };
  await fetchHealth(undefined, production);
  await fetchScenarios(undefined, production);
  await runAnalysis("compute_spike", false, undefined, production);
  await fetchDecisions(undefined, production);
  await fetchApprovals(undefined, production);
  assert.equal(await fetchLatestAnalysis(undefined, production), null);
  await submitApprovalDecision("appr-1", "approved", "ok", undefined, production);
  assert.deepEqual(calls.map((call) => [call.path, call.method]), [
    ["/api/health", "GET"], ["/api/demo/scenarios", "GET"], ["/api/analyze", "POST"],
    ["/api/decisions?limit=15", "GET"], ["/api/approvals", "GET"], ["/api/analysis/latest", "GET"],
    ["/api/approvals/appr-1/decision", "POST"],
  ]);
  for (const call of calls.filter((item) => item.method === "GET")) assert.equal(call.headers.has("Content-Type"), false);
  assert.deepEqual(JSON.parse(String(calls[2].body)), { scenario_id: "compute_spike", use_aws_cost_explorer: false });
  assert.deepEqual(JSON.parse(String(calls[6].body)), { action: "approved", notes: "ok" });
});

test("request timeout is reported as a recoverable API error", async () => {
  const originalTimeout = AbortSignal.timeout;
  const timeoutController = new AbortController();
  Object.defineProperty(AbortSignal, "timeout", { configurable: true, value: () => timeoutController.signal });
  globalThis.fetch = async (_input, init) => new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(init.signal?.reason), { once: true });
    timeoutController.abort(new DOMException("Timed out", "TimeoutError"));
  });
  try {
    await assert.rejects(requestJson("/api/health", {}, "Health", production), /timed out/i);
  } finally {
    Object.defineProperty(AbortSignal, "timeout", { configurable: true, value: originalTimeout });
  }
});

test("latest analysis restores its source and partial-data warnings", async () => {
  const latest = {
    anomaly: { anomaly_id: "analysis-1", service: "Amazon EC2", metrics: {}, time_series: [], is_simulated: false },
    decision: { decision_id: "decision-1", action: "monitor", timestamp: "2026-11-08T00:00:00Z", provider: "rules" },
    report: { report_id: "report-1", anomaly_id: "analysis-1", decision_id: "decision-1", observed_facts: [], safe_recommendations: [] },
    approval: null, is_simulated: false, cost_data_source: "aws_cost_explorer", partial_data: true,
    data_warnings: ["PARTIAL_DATA: one day of cost data is missing"],
  };
  globalThis.fetch = async (input) => {
    assert.equal(new URL(String(input)).pathname, "/api/analysis/latest");
    return new Response(JSON.stringify(latest), { status: 200 });
  };
  const restored = await fetchLatestAnalysis(undefined, production);
  assert.equal(restored?.anomaly.anomaly_id, "analysis-1");
  assert.equal(restored?.partial_data, true);
  assert.deepEqual(restored?.data_warnings, latest.data_warnings);
});

test("account profile reads and updates use the authenticated profile endpoint", async () => {
  const calls: Array<{ path: string; method: string; body: BodyInit | null | undefined }> = [];
  globalThis.fetch = async (input, init) => {
    const url = new URL(String(input));
    calls.push({ path: url.pathname, method: init?.method ?? "GET", body: init?.body });
    return new Response(JSON.stringify({ user_id: "user-1", display_name: "FinOps lead", organization_id: "org-1", role: "admin" }), { status: 200 });
  };
  const profile = await fetchAccountProfile(undefined, production);
  assert.equal(profile.user_id, "user-1");
  await updateAccountProfile("  FinOps lead  ", undefined, production);
  await updateAccountProfile("   ", undefined, production);
  assert.deepEqual(calls.map(({ path, method }) => [path, method]), [
    ["/api/account/profile", "GET"], ["/api/account/profile", "PUT"], ["/api/account/profile", "PUT"],
  ]);
  assert.deepEqual(JSON.parse(String(calls[1].body)), { display_name: "FinOps lead" });
  assert.deepEqual(JSON.parse(String(calls[2].body)), { display_name: null });
});

test("AWS account integration uses the tenant-scoped authenticated endpoints", async () => {
  const calls: Array<{ path: string; method: string; body: BodyInit | null | undefined }> = [];
  const connection = { organization_id: "org-1", role_arn: "arn:aws:iam::123456789012:role/CloudCostSentinelReadOnly", external_id: "a".repeat(32), account_id: "123456789012", status: "pending", verified_at: null, updated_at: "2026-01-01T00:00:00Z" };
  globalThis.fetch = async (input, init) => {
    const url = new URL(String(input)); calls.push({ path: url.pathname, method: init?.method ?? "GET", body: init?.body });
    const payload = url.pathname.endsWith("/verify") ? { status: "connected", account_id: "123456789012", verified_at: "2026-01-01T00:00:00Z" }
      : init?.method === "PUT" ? { connection, platform_principal_arn: "arn:aws:iam::000000000000:user/platform", instructions: "Set customer trust." }
        : init?.method === "DELETE" ? { status: "disconnected" }
      : { enabled: true, daily_query_limit: 20, connection, platform_principal_arn: "arn:aws:iam::000000000000:user/platform" };
    return new Response(JSON.stringify(payload), { status: 200 });
  };
  assert.equal((await fetchAwsIntegration(undefined, production)).connection?.status, "pending");
  await connectAwsIntegration(connection.role_arn, production);
  await verifyAwsIntegration(production);
  await disconnectAwsIntegration(production);
  assert.deepEqual(calls.map(({ path, method }) => [path, method]), [
    ["/api/integrations/aws", "GET"], ["/api/integrations/aws", "PUT"],
    ["/api/integrations/aws/verify", "POST"], ["/api/integrations/aws", "DELETE"],
  ]);
  assert.deepEqual(JSON.parse(String(calls[1].body)), { role_arn: connection.role_arn });
});

