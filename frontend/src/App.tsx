import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import { Header } from "./components/Header";
import { ScenarioControls } from "./components/ScenarioControls";
import { OverviewCards } from "./components/OverviewCards";
import { SpendChart } from "./components/SpendChart";
import { DecisionPanel } from "./components/DecisionPanel";
import { BedrockReportPanel } from "./components/BedrockReportPanel";
import { ApprovalsFeed } from "./components/ApprovalsFeed";
import type { ApprovalItem, CostAnomaly, DeciderResponseTrace, BedrockReport, HealthInfo, Scenario } from "./types";
import { ApiError, fetchHealth, fetchScenarios, runAnalysis, fetchApprovals, fetchDecisions, submitApprovalDecision } from "./api";

type ResourceKey = "health" | "scenarios" | "decisions" | "approvals";
type ResourceErrors = Record<ResourceKey, ApiError | Error | null>;

export const App = () => {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState("compute_spike");
  const [anomaly, setAnomaly] = useState<CostAnomaly | null>(null);
  const [decision, setDecision] = useState<DeciderResponseTrace | null>(null);
  const [decisionHistory, setDecisionHistory] = useState<DeciderResponseTrace[]>([]);
  const [report, setReport] = useState<BedrockReport | null>(null);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [resourceErrors, setResourceErrors] = useState<ResourceErrors>({ health: null, scenarios: null, decisions: null, approvals: null });
  const [analysisError, setAnalysisError] = useState<ApiError | Error | null>(null);
  const [dataWarning, setDataWarning] = useState<string | null>(null);
  const [costDataSource, setCostDataSource] = useState<string | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<Set<string>>(() => new Set());
  const mounted = useRef(true);
  const analysisRequest = useRef<AbortController | null>(null);
  const resourceRequest = useRef<AbortController | null>(null);
  const toastTimer = useRef<number | null>(null);
  const selectedIdRef = useRef(selectedScenarioId);
  const hasAnomalyRef = useRef(Boolean(anomaly));

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      analysisRequest.current?.abort();
      resourceRequest.current?.abort();
      if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    };
  }, []);

  const notify = (text: string, error = false) => {
    setToast({ text, error });
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 5000);
  };

  const executeAnalysis = useCallback(async (scenarioId: string) => {
    analysisRequest.current?.abort();
    const controller = new AbortController();
    analysisRequest.current = controller;
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      const result = await runAnalysis(scenarioId, false, controller.signal);
      if (!mounted.current || controller.signal.aborted) return;
      hasAnomalyRef.current = true;
      setAnomaly(result.anomaly);
      setDecision(result.decision);
      setDecisionHistory((current) => [result.decision, ...current.filter((item) => item.decision_id !== result.decision.decision_id)].slice(0, 15));
      setReport(result.report);
      setCostDataSource(result.cost_data_source);
      setDataWarning(result.partial_data ? result.data_warnings.join(" ") : null);
      if (result.approval) setApprovals((current) => [result.approval!, ...current.filter((item) => item.id !== result.approval!.id)]);
    } catch (error) {
      if (controller.signal.aborted) return;
      if (mounted.current) setAnalysisError(error instanceof Error ? error : new Error("Analysis failed."));
    } finally {
      if (mounted.current && analysisRequest.current === controller) setAnalyzing(false);
    }
  }, []);

  const refreshResources = useCallback(async (signal: AbortSignal, runInitialAnalysis = false) => {
    const results = await Promise.allSettled([
      fetchHealth(signal), fetchScenarios(signal), fetchDecisions(signal), fetchApprovals(signal),
    ]);
    if (!mounted.current || signal.aborted) return;
    const [healthResult, scenarioResult, decisionResult, approvalResult] = results;
    setResourceErrors({
      health: healthResult.status === "rejected" ? toError(healthResult.reason) : null,
      scenarios: scenarioResult.status === "rejected" ? toError(scenarioResult.reason) : null,
      decisions: decisionResult.status === "rejected" ? toError(decisionResult.reason) : null,
      approvals: approvalResult.status === "rejected" ? toError(approvalResult.reason) : null,
    });
    if (healthResult.status === "fulfilled") setHealth(healthResult.value);
    if (scenarioResult.status === "fulfilled" && scenarioResult.value.length === 0) {
      setResourceErrors((current) => ({ ...current, scenarios: new Error("The backend returned no scenarios. Check configuration and retry.") }));
    }
    if (scenarioResult.status === "fulfilled") {
      setScenarios(scenarioResult.value);
      if (scenarioResult.value.length > 0) {
        const selectedStillExists = scenarioResult.value.some((scenario) => scenario.id === selectedIdRef.current);
        const nextId = selectedStillExists ? selectedIdRef.current
          : scenarioResult.value.find((scenario) => scenario.id === "compute_spike")?.id ?? scenarioResult.value[0].id;
        selectedIdRef.current = nextId;
        setSelectedScenarioId(nextId);
        if (runInitialAnalysis && !hasAnomalyRef.current) await executeAnalysis(nextId);
      }
    }
    if (decisionResult.status === "fulfilled") setDecisionHistory(decisionResult.value);
    if (approvalResult.status === "fulfilled") setApprovals(approvalResult.value);
    setLastChecked(new Date());
    setInitializing(false);
    setRefreshing(false);
  }, [executeAnalysis]);

  useEffect(() => {
    const controller = new AbortController();
    resourceRequest.current = controller;
    void refreshResources(controller.signal, true);
    return () => controller.abort();
  }, [refreshResources]);

  const handleRefresh = () => {
    setRefreshing(true);
    resourceRequest.current?.abort();
    const controller = new AbortController();
    resourceRequest.current = controller;
    void refreshResources(controller.signal, false);
  };

  const handleRetry = () => {
    if (resourceErrors.scenarios || resourceErrors.health || resourceErrors.approvals || resourceErrors.decisions) {
      handleRefresh();
    }
    if (analysisError && scenarios.length > 0) void executeAnalysis(selectedScenarioId);
  };

  const handleScenario = (id: string) => {
    selectedIdRef.current = id;
    setSelectedScenarioId(id);
    void executeAnalysis(id);
  };

  const decideApproval = async (id: string, action: "approved" | "rejected") => {
    setPendingApprovals((current) => new Set(current).add(id));
    try {
      const updated = await submitApprovalDecision(id, action);
      if (!mounted.current) return;
      setApprovals((current) => current.map((item) => item.id === id ? updated : item));
      notify(`Approval recorded as ${action}.`);
    } catch (error) {
      if (!mounted.current) return;
      const failure = toError(error);
      notify(`${failure.message}${failure instanceof ApiError && failure.requestId ? ` (Request ID: ${failure.requestId})` : ""}`, true);
      if (failure instanceof ApiError && failure.status === 409) handleRefresh();
    } finally {
      if (mounted.current) setPendingApprovals((current) => {
        const next = new Set(current);
        next.delete(id);
        return next;
      });
    }
  };

  const failedResources = Object.entries(resourceErrors).filter(([, error]) => error !== null) as [ResourceKey, Error][];
  const backendUnreachable = !health && Boolean(resourceErrors.health);
  const resourceLabels: Record<ResourceKey, string> = { health: "Backend health", scenarios: "Scenario list", decisions: "Decision history", approvals: "Approvals" };

  return (
    <main className="app-shell">
      <Header health={health} isSimulated={anomaly ? anomaly.is_simulated : null} />
      <section className="page-intro" aria-labelledby="page-title">
        <div>
          <p className="eyebrow"><Activity size={14} /> FINOPS OPERATIONS CONSOLE</p>
          <h1 id="page-title">Cloud spend, under control.</h1>
          <p>Review cost signals, understand recommended actions, and keep every decision auditable.</p>
        </div>
        <div className="connection-actions">
          <span className={`connection-label ${backendUnreachable ? "is-offline" : failedResources.length ? "is-warning" : health ? "is-online" : ""}`} role="status">
            {initializing ? "Connecting to API…" : backendUnreachable ? "API unreachable" : failedResources.length ? "Some data needs attention" : "API connected"}
          </span>
          <button type="button" className="btn btn-secondary" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw size={15} className={refreshing ? "spin" : undefined} />
            {refreshing ? "Checking…" : "Check connection"}
          </button>
          <span className="last-checked">{lastChecked ? `Checked ${lastChecked.toLocaleTimeString()}` : "Not checked yet"}</span>
        </div>
      </section>

      {health?.environment === "demo" && (
        <div className="public-demo-notice" role="status"><strong>SIMULATED DEMO</strong> · Synthetic cost data only. Provider responses are simulated, records may be shared, and no AWS action is executed.</div>
      )}
      {health?.auth?.enabled && health.auth.mode === "jwt_bearer" && (
        <div className="auth-notice" role="status">This API requires an authorized account. Actions are checked by the backend; this dashboard does not provide sign-in.</div>
      )}

      {initializing && <div className="loading-panel" role="status"><span className="spinner" /> Connecting to the CloudCost Sentinel API and loading dashboard data…</div>}
      {backendUnreachable && <div className="error-panel" role="alert">
        <div><strong>API unreachable</strong><p>{resourceErrors.health?.message}{resourceErrors.health instanceof ApiError && resourceErrors.health.endpoint ? ` · ${resourceErrors.health.endpoint}` : ""}{resourceErrors.health instanceof ApiError && resourceErrors.health.status ? ` · HTTP ${resourceErrors.health.status}` : ""}. Check that the frontend was built with <code>VITE_API_BASE_URL</code>, Render is public and awake, and its CORS allowlist includes this site.</p></div>
        <button className="btn btn-secondary" onClick={handleRefresh} disabled={refreshing}>Retry</button>
      </div>}
      {failedResources.length > 0 && !initializing && <div className="resource-errors" aria-label="Dashboard data warnings">
        {failedResources.map(([key, error]) => <div key={key} className="error-panel compact" role="alert">
          <div><strong>{resourceLabels[key]} could not be refreshed</strong><p>{error.message}{error instanceof ApiError && error.endpoint ? ` · ${error.endpoint}` : ""}{error instanceof ApiError && error.status ? ` · HTTP ${error.status}` : ""}{error instanceof ApiError && error.requestId ? ` · Request ID: ${error.requestId}` : ""}{health && " · Showing the last available data where possible."}</p></div>
          <button className="btn btn-secondary btn-sm" onClick={handleRefresh} disabled={refreshing}>Retry</button>
        </div>)}
      </div>}

      <ScenarioControls
        scenarios={scenarios}
        selectedScenarioId={selectedScenarioId}
        onSelectScenario={handleScenario}
        onRunAnalysis={() => void executeAnalysis(selectedScenarioId)}
        onSimulateSpike={() => handleScenario(scenarios.some((scenario) => scenario.id === "compute_spike") ? "compute_spike" : selectedScenarioId)}
        onReset={() => handleScenario(scenarios.some((scenario) => scenario.id === "stable_baseline") ? "stable_baseline" : selectedScenarioId)}
        loading={analyzing || refreshing || initializing}
        scenariosError={resourceErrors.scenarios?.message ?? null}
        onRetryScenarios={handleRefresh}
      />

      {analysisError && <div className="error-panel" role="alert"><div><strong>Analysis did not complete</strong><p>{analysisError.message}{analysisError instanceof ApiError && analysisError.endpoint ? ` · ${analysisError.endpoint}` : ""}{analysisError instanceof ApiError && analysisError.status ? ` · HTTP ${analysisError.status}` : ""}{analysisError instanceof ApiError && analysisError.requestId ? ` · Request ID: ${analysisError.requestId}` : ""}</p></div><button className="btn btn-secondary" onClick={handleRetry} disabled={analyzing || scenarios.length === 0}>Retry analysis</button></div>}
      {anomaly && <div className="analysis-context"><span>Current analysis: <strong>{anomaly.scenario_name}</strong> · {anomaly.service} / {anomaly.environment}</span>{anomaly.scenario_id !== selectedScenarioId && <span className="stale-tag">Showing previous result while the selected scenario updates</span>}</div>}
      {dataWarning && <div role="alert" className="public-demo-notice">PARTIAL COST DATA — {dataWarning}</div>}
      {costDataSource && <div className="data-source-label">Cost source: {costDataSource.replaceAll("_", " ")}</div>}

      {toast && <div className={`toast ${toast.error ? "toast-error" : "toast-success"}`} role={toast.error ? "alert" : "status"} aria-live={toast.error ? "assertive" : "polite"}>{toast.text}<button type="button" onClick={() => setToast(null)} aria-label="Dismiss notification">×</button></div>}

      {anomaly && <OverviewCards metrics={anomaly.metrics} service={anomaly.service} environment={anomaly.environment} />}
      {!anomaly && !initializing && !analysisError && <div className="empty-panel">Choose a scenario and run an analysis to see cost signals and recommendations.</div>}

      <div className="dashboard-grid">
        <div className="dashboard-column">
          {anomaly ? <SpendChart data={anomaly.time_series} baseline={anomaly.metrics.baseline_spend} service={anomaly.service} /> : <section className="panel-card empty-panel"><h2>Spend telemetry</h2><p>Chart data will appear after a scenario analysis completes.</p></section>}
          {report ? <BedrockReportPanel report={report} /> : <section className="panel-card empty-panel"><h2>Investigation report</h2><p>Grounded recommendations will appear after analysis. Provider mode is reported by the API above.</p></section>}
        </div>
        <div className="dashboard-column">
          {decision ? <DecisionPanel decision={decision} /> : <section className="panel-card empty-panel"><h2>Decision recommendation</h2><p>The policy recommendation will appear after analysis.</p></section>}
          <section className="panel-card history-panel">
            <div className="panel-header"><h2 className="panel-title">Recent decisions</h2><span className="status-pill">{decisionHistory.length} loaded</span></div>
            {resourceErrors.decisions && !decisionHistory.length ? <p className="inline-error">Decision history is unavailable. Retry the connection check.</p>
              : decisionHistory.length ? <ul>{decisionHistory.slice(0, 5).map((item) => <li key={item.decision_id}><span>{item.action.replaceAll("_", " ")}</span><span>{item.provider}</span><time>{new Date(item.timestamp).toLocaleString()}</time></li>)}</ul>
                : <p className="empty-copy">No decisions recorded yet. Run a scenario analysis to begin.</p>}
          </section>
          <ApprovalsFeed approvals={approvals} onDecide={decideApproval} pendingIds={pendingApprovals} error={resourceErrors.approvals?.message ?? null} />
        </div>
      </div>
      <footer className="app-footer">CloudCost Sentinel · Decision support only · No automatic cloud mutations</footer>
    </main>
  );
};

function toError(error: unknown): Error {
  if (error instanceof Error) return error;
  return new Error("The dashboard resource could not be loaded. Retry the request.");
}

export default App;
