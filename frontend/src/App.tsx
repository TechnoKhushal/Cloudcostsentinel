import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import { ScenarioControls } from "./components/ScenarioControls";
import { OverviewCards } from "./components/OverviewCards";
import { DecisionPanel } from "./components/DecisionPanel";
import { InvestigationReportPanel } from "./components/InvestigationReportPanel";
import { ApprovalsFeed } from "./components/ApprovalsFeed";
import { WorkspaceHeader, type WorkspaceScreen } from "./components/WorkspaceHeader";
import { LandingPage } from "./components/LandingPage";
import { CostExplorerPage } from "./components/CostExplorerPage";
import { FindingsPage } from "./components/FindingsPage";
import { AccountSettingsPage, IntegrationsPage } from "./components/ServicePages";
import type { ApprovalItem, CostAnomaly, DeciderResponseTrace, InvestigationReport, HealthInfo, Scenario } from "./types";
import { ApiError, fetchHealth, fetchScenarios, runAnalysis, fetchApprovals, fetchDecisions, submitApprovalDecision, downloadPrivateReport } from "./api";
import { buildAnalysisCsv, buildExecutiveBrief, downloadAnalysisCsv } from "./analysisExport";

const SpendChart = lazy(() => import("./components/SpendChart").then(({ SpendChart }) => ({ default: SpendChart })));
type ResourceKey = "health" | "scenarios" | "decisions" | "approvals";
type ResourceErrors = Record<ResourceKey, ApiError | Error | null>;
const pageIds: WorkspaceScreen[] = ["overview", "costs", "findings", "recommendations", "reports", "integrations", "settings", "landing"];

function readScreen(): WorkspaceScreen {
  const id = window.location.hash.slice(1) as WorkspaceScreen;
  return pageIds.includes(id) ? id : "overview";
}

export const App = () => {
  const [screen, setScreen] = useState<WorkspaceScreen>(readScreen);
  const [query, setQuery] = useState("");
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState("compute_spike");
  const [anomaly, setAnomaly] = useState<CostAnomaly | null>(null);
  const [decision, setDecision] = useState<DeciderResponseTrace | null>(null);
  const [decisionHistory, setDecisionHistory] = useState<DeciderResponseTrace[]>([]);
  const [report, setReport] = useState<InvestigationReport | null>(null);
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
    const updateScreen = () => setScreen(readScreen());
    window.addEventListener("hashchange", updateScreen);
    const focusSearch = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        document.getElementById("global-filter")?.focus();
      }
    };
    window.addEventListener("keydown", focusSearch);
    mounted.current = true;
    return () => {
      mounted.current = false;
      window.removeEventListener("hashchange", updateScreen);
      window.removeEventListener("keydown", focusSearch);
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
      const result = await runAnalysis(scenarioId, scenarioId === "__aws_cost_explorer__", controller.signal);
      if (!mounted.current || controller.signal.aborted) return;
      hasAnomalyRef.current = true;
      setAnomaly(result.anomaly);
      setDecision(result.decision);
      setDecisionHistory((current) => [result.decision, ...current.filter((item) => item.decision_id !== result.decision.decision_id)].slice(0, 30));
      setReport(result.report);
      setCostDataSource(result.cost_data_source);
      setDataWarning(result.data_warnings.length > 0 ? result.data_warnings.join(" ") : null);
      if (result.approval) setApprovals((current) => [result.approval!, ...current.filter((item) => item.id !== result.approval!.id)]);
    } catch (error) {
      if (controller.signal.aborted) return;
      if (mounted.current) setAnalysisError(error instanceof Error ? error : new Error("Analysis failed."));
    } finally {
      if (mounted.current && analysisRequest.current === controller) setAnalyzing(false);
    }
  }, []);

  const refreshResources = useCallback(async (signal: AbortSignal, runInitialAnalysis = false) => {
    const results = await Promise.allSettled([fetchHealth(signal), fetchScenarios(signal), fetchDecisions(signal), fetchApprovals(signal)]);
    if (!mounted.current || signal.aborted) return;
    const [healthResult, scenarioResult, decisionResult, approvalResult] = results;
    setResourceErrors({
      health: healthResult.status === "rejected" ? toError(healthResult.reason) : null,
      scenarios: scenarioResult.status === "rejected" ? toError(scenarioResult.reason) : null,
      decisions: decisionResult.status === "rejected" ? toError(decisionResult.reason) : null,
      approvals: approvalResult.status === "rejected" ? toError(approvalResult.reason) : null,
    });
    if (healthResult.status === "fulfilled") setHealth(healthResult.value);
    if (scenarioResult.status === "fulfilled" && scenarioResult.value.length === 0 && !(healthResult.status === "fulfilled" && healthResult.value.environment === "production")) {
      setResourceErrors((current) => ({ ...current, scenarios: new Error("The backend returned no scenarios. Check configuration and retry.") }));
    }
    if (scenarioResult.status === "fulfilled") {
      setScenarios(scenarioResult.value);
      if (scenarioResult.value.length > 0) {
        const selectedStillExists = scenarioResult.value.some((scenario) => scenario.id === selectedIdRef.current);
        const nextId = selectedStillExists ? selectedIdRef.current : scenarioResult.value.find((scenario) => scenario.id === "compute_spike")?.id ?? scenarioResult.value[0].id;
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
    const timer = window.setTimeout(() => { void refreshResources(controller.signal, true); }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [refreshResources]);

  const handleRefresh = () => {
    setRefreshing(true);
    resourceRequest.current?.abort();
    const controller = new AbortController();
    resourceRequest.current = controller;
    void refreshResources(controller.signal, false);
  };
  const handleRetry = () => {
    if (Object.values(resourceErrors).some(Boolean)) handleRefresh();
    if (analysisError && scenarios.length > 0) void executeAnalysis(selectedScenarioId);
  };
  const handleExport = () => {
    if (!anomaly || !decision || !report) return;
    downloadAnalysisCsv(buildAnalysisCsv(anomaly, decision, report), anomaly.scenario_id);
    notify("Current API analysis exported as CSV.");
  };
  const handleCopyBrief = async () => {
    if (!anomaly || !decision || !report) return;
    try { await navigator.clipboard.writeText(buildExecutiveBrief(anomaly, decision, report)); notify("Evidence brief copied."); }
    catch { notify("Clipboard access is unavailable. Use CSV export instead.", true); }
  };
  const handleReportDownload = async () => {
    if (!report) return;
    try { await downloadPrivateReport(report.report_id); notify("Private report downloaded."); }
    catch (error) { notify(toError(error).message, true); }
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
      if (mounted.current) setPendingApprovals((current) => { const next = new Set(current); next.delete(id); return next; });
    }
  };

  const failedResources = Object.entries(resourceErrors).filter(([, error]) => error !== null) as [ResourceKey, Error][];
  const backendUnreachable = !health && Boolean(resourceErrors.health);
  const resourceLabels: Record<ResourceKey, string> = { health: "Backend health", scenarios: "Scenario list", decisions: "Decision history", approvals: "Approvals" };
  const filteredDecisions = decisionHistory.filter((item) => !query || `${item.action} ${item.provider} ${item.decision_id}`.toLowerCase().includes(query.toLowerCase()));
  const supabaseProfileEnabled = Boolean(health?.auth?.enabled && health.persistence?.provider === "supabase");

  return (
    <div className="app-frame">
      <WorkspaceHeader active={screen} health={health} query={query} onQueryChange={setQuery} />
      {screen === "landing" && <LandingPage health={health} hasAnalysis={Boolean(anomaly)} />}
      {screen === "costs" && <CostExplorerPage anomaly={anomaly} query={query} />}
      {screen === "findings" && <FindingsPage anomaly={anomaly} decision={decision} report={report} approvals={approvals} query={query} canDownload={health?.persistence?.provider === "supabase"} onDownloadReport={() => void handleReportDownload()} />}
      {screen === "integrations" && <IntegrationsPage health={health} />}
      {screen === "settings" && <AccountSettingsPage enabled={supabaseProfileEnabled} />}
      {screen === "overview" && <main className="page-content overview-page">
        <section className="overview-heading">
          <div><p className="eyebrow"><Activity size={14} /> EXECUTIVE LEDGER BRIEF <span className="eyebrow-separator">/</span> API-VERIFIED DATA</p><h1>Infrastructure fiscal <em>pulse</em></h1><p className="page-lede">Review cost signals, their evidence, and the policy response. Every value below comes from the current API response.</p></div>
          <div className="overview-heading-actions"><span className={`connection-label ${backendUnreachable ? "is-offline" : failedResources.length ? "is-warning" : health ? "is-online" : ""}`} role="status">{initializing ? "Connecting to API" : backendUnreachable ? "API unavailable" : failedResources.length ? "Some data unavailable" : "API connected"}</span><button type="button" className="action-secondary compact-action" onClick={handleRefresh} disabled={refreshing}><RefreshCw size={14} className={refreshing ? "spin" : undefined} />{refreshing ? "Checking…" : "Refresh"}</button>{anomaly && decision && report && <button type="button" className="action-secondary compact-action" onClick={() => void handleCopyBrief()}>Copy evidence brief</button>}<span className="last-checked">{lastChecked ? `Checked ${lastChecked.toLocaleTimeString()}` : "Not checked"}</span></div>
        </section>
        {initializing && <div className="loading-panel" role="status"><span className="spinner" /> Loading verified workspace data…</div>}
        {backendUnreachable && <div className="error-panel" role="alert"><div><strong>API unavailable</strong><p>{resourceErrors.health?.message ?? "The backend could not be reached. Check VITE_API_BASE_URL and retry."}</p></div><button className="action-secondary compact-action" onClick={handleRefresh} disabled={refreshing}>Retry</button></div>}
        {failedResources.length > 0 && !initializing && <div className="resource-errors" aria-label="Dashboard data warnings">{failedResources.map(([key, error]) => <div key={key} className="error-panel compact" role="alert"><div><strong>{resourceLabels[key]} could not be refreshed</strong><p>{error.message}</p></div><button className="action-secondary compact-action" onClick={handleRefresh} disabled={refreshing}>Retry</button></div>)}</div>}
        <ScenarioControls scenarios={scenarios} selectedScenarioId={selectedScenarioId} onSelectScenario={handleScenario} onRunAnalysis={() => void executeAnalysis(selectedScenarioId)} onSimulateSpike={() => handleScenario(scenarios.some((scenario) => scenario.id === "compute_spike") ? "compute_spike" : selectedScenarioId)} onReset={() => handleScenario(scenarios.some((scenario) => scenario.id === "stable_baseline") ? "stable_baseline" : selectedScenarioId)} loading={analyzing || refreshing || initializing} scenariosError={resourceErrors.scenarios?.message ?? null} onRetryScenarios={handleRefresh} productionMode={health?.environment === "production"} costExplorerEnabled={health?.providers.cost_explorer.enabled ?? false} onRunLiveAnalysis={() => void executeAnalysis("__aws_cost_explorer__")} />
        {analysisError && <div className="error-panel" role="alert"><div><strong>Analysis did not complete</strong><p>{analysisError.message}</p></div><button className="action-secondary compact-action" onClick={handleRetry} disabled={analyzing}>Retry analysis</button></div>}
        {dataWarning && <div role="alert" className="data-quality-notice"><strong>COST DATA NOTICE</strong> · {dataWarning}</div>}
        {costDataSource && anomaly && <div className="data-provenance-line"><span>DATA SOURCE</span><strong>{costDataSource.replaceAll("_", " ")}</strong><span>ANALYSIS ID</span><code>{anomaly.anomaly_id}</code><span>AS OF</span><time>{new Date(anomaly.detected_at).toLocaleString()}</time></div>}
        {anomaly && <OverviewCards metrics={anomaly.metrics} service={anomaly.service} environment={anomaly.environment} />}
        {!anomaly && !initializing && !analysisError && <section className="empty-state"><span className="eyebrow">NO ANALYSIS LOADED</span><h2>{health?.environment === "production" ? "Connect your AWS billing account to begin." : "Choose a scenario to inspect its cost evidence."}</h2><p>{health?.environment === "production" ? "Production analyzes verified AWS Cost Explorer data for your personal workspace. Connect and verify a customer-owned read-only role, then set your monthly budget and currency." : "Run an analysis to display its returned metrics and time series."}</p>{health?.environment === "production" && <div className="page-actions"><a className="action-primary" href="#integrations">Connect AWS</a><a className="action-secondary" href="#settings">Set budget</a></div>}</section>}
        {anomaly && <>
          <div className="overview-body-grid">
            <div className="overview-main-column">
              <section className="ledger-panel trend-panel"><div className="ledger-panel-heading"><div><span className="eyebrow">OBSERVED SERIES</span><h2>Daily burn &amp; moving baseline</h2></div><span className="provenance observed">{anomaly.is_simulated ? "SYNTHETIC" : "OBSERVED"}</span></div><Suspense fallback={<div className="chart-loading">Loading chart…</div>}><SpendChart data={anomaly.time_series} baseline={anomaly.metrics.baseline_spend} service={anomaly.service} /></Suspense><div className="chart-caption"><span>Observed spend</span><span>Baseline {anomaly.currency} {anomaly.metrics.baseline_spend.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span><span>Source: {costDataSource?.replaceAll("_", " ") ?? "API analysis"}</span></div></section>
              {report ? <InvestigationReportPanel report={report} canDownload={health?.persistence?.provider === "supabase"} onDownload={() => void handleReportDownload()} /> : <section className="ledger-panel"><h2>Investigation report</h2><p className="empty-copy">The API has not returned a report for this analysis.</p></section>}
            </div>
            <aside className="overview-side-column">
              {decision ? <DecisionPanel decision={decision} /> : <section className="ledger-panel"><h2>Decision recommendation</h2><p className="empty-copy">No decision was returned.</p></section>}
              <section className="ledger-panel history-panel"><div className="ledger-panel-heading"><div><span className="eyebrow">IMMUTABLE DECISION TRACE</span><h2>Recent decisions</h2></div><a className="text-link" href="#recommendations">View history <span aria-hidden="true">→</span></a></div>{resourceErrors.decisions && !decisionHistory.length ? <p className="inline-error">Decision history is unavailable: {resourceErrors.decisions.message}</p> : filteredDecisions.length ? <ul>{filteredDecisions.slice(0, 6).map((item) => <li key={item.decision_id}><span>{item.action.replaceAll("_", " ")}</span><span>{item.provider}</span><time>{new Date(item.timestamp).toLocaleString()}</time></li>)}</ul> : <p className="empty-copy">{query ? "No decisions match the current filter." : "No decisions were returned."}</p>}</section>
              <ApprovalsFeed approvals={approvals} onDecide={decideApproval} pendingIds={pendingApprovals} error={resourceErrors.approvals?.message ?? null} />
            </aside>
          </div>
          <section className="overview-ledger-footer"><div><span className="eyebrow">WORKING WITH THIS RESULT</span><strong>Open the cost series, inspect the finding, or review the policy queue.</strong></div><div><a className="action-secondary compact-action" href="#costs">Explore cost series <span aria-hidden="true">→</span></a><a className="action-secondary compact-action" href="#findings">Inspect evidence <span aria-hidden="true">→</span></a></div></section>
        </>}
      </main>}
      {screen === "recommendations" && <main className="page-content"><div className="page-heading-row"><div><p className="eyebrow">POLICY &amp; HUMAN REVIEW</p><h1>Recommendations <em>&amp; approvals</em></h1><p className="page-lede">Recommendations explain the API decision. Approval transitions update internal review state only.</p></div></div><div className="recommendation-grid">{decision ? <DecisionPanel decision={decision} /> : <section className="empty-state"><h2>No decision trace</h2><p>Run an analysis to view its recommendation.</p><a className="action-primary" href="#overview">Go to Overview</a></section>}<ApprovalsFeed approvals={approvals} onDecide={decideApproval} pendingIds={pendingApprovals} error={resourceErrors.approvals?.message ?? null} /></div></main>}
      {screen === "reports" && <main className="page-content"><div className="page-heading-row"><div><p className="eyebrow">REPORTS &amp; EXPORTS</p><h1>Analysis <em>reports</em></h1><p className="page-lede">The current API provides the most recent analysis in this browser session. A report history endpoint is not available yet.</p></div><div className="page-actions">{anomaly && decision && report && <button className="action-secondary compact-action" onClick={handleExport}><span aria-hidden="true">↓</span>Export analysis CSV</button>}</div></div>{report ? <><div className="report-source-card"><span className="provenance observed">CURRENT SESSION REPORT</span><span>{report.generated_at}</span><span>{report.provider} · {report.model_id}</span></div><InvestigationReportPanel report={report} canDownload={health?.persistence?.provider === "supabase"} onDownload={() => void handleReportDownload()} /></> : <section className="empty-state"><h2>No report is available.</h2><p>Run an analysis. Reports are not fabricated when the API has no result.</p><a className="action-primary" href="#overview">Go to Overview</a></section>}</main>}
      {screen !== "overview" && screen !== "landing" && screen !== "costs" && screen !== "findings" && screen !== "recommendations" && screen !== "reports" && screen !== "integrations" && screen !== "settings" && <main className="page-content"><p>Unknown page.</p></main>}
      <footer className="workspace-footer"><a href="#landing">CLOUDCOST SENTINEL</a><span>Editorial FinOps observability</span><span>Decision support only · No automatic cloud changes</span><span>Mode: {health?.environment ?? "checking"}</span></footer>
      {toast && <div className={`toast ${toast.error ? "toast-error" : "toast-success"}`} role={toast.error ? "alert" : "status"} aria-live={toast.error ? "assertive" : "polite"}>{toast.text}<button type="button" onClick={() => setToast(null)} aria-label="Dismiss notification">×</button></div>}
    </div>
  );
};

function toError(error: unknown): Error {
  if (error instanceof Error) return error;
  return new Error("The dashboard resource could not be loaded. Retry the request.");
}

export default App;
