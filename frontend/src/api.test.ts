import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { ApiError, apiUrl, fetchApprovals, fetchDecisions, fetchHealth, fetchScenarios, requestJson, resolveApiBase, runAnalysis, submitApprovalDecision } from "./api.ts";

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
    if (url.pathname === "/api/health") payload = { environment: "demo", providers: { decider: {}, bedrock: {}, cost_explorer: {} } };
    if (url.pathname === "/api/analyze") payload = { anomaly: { metrics: {}, time_series: [] }, decision: {}, report: { observed_facts: [], safe_recommendations: [] }, is_simulated: true, cost_data_source: "synthetic_scenario", partial_data: false, data_warnings: [] };
    if (url.pathname === "/api/approvals/appr-1/decision") payload = approval;
    return new Response(JSON.stringify(payload), { status: 200 });
  };
  await fetchHealth(undefined, production);
  await fetchScenarios(undefined, production);
  await runAnalysis("compute_spike", false, undefined, production);
  await fetchDecisions(undefined, production);
  await fetchApprovals(undefined, production);
  await submitApprovalDecision("appr-1", "approved", "ok", undefined, production);
  assert.deepEqual(calls.map((call) => [call.path, call.method]), [
    ["/api/health", "GET"], ["/api/demo/scenarios", "GET"], ["/api/analyze", "POST"],
    ["/api/decisions?limit=15", "GET"], ["/api/approvals", "GET"], ["/api/approvals/appr-1/decision", "POST"],
  ]);
  for (const call of calls.filter((item) => item.method === "GET")) assert.equal(call.headers.has("Content-Type"), false);
  assert.deepEqual(JSON.parse(String(calls[2].body)), { scenario_id: "compute_spike", use_aws_cost_explorer: false });
  assert.deepEqual(JSON.parse(String(calls[5].body)), { action: "approved", notes: "ok" });
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

