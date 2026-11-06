import { AlertTriangle, CheckCircle, Search } from "lucide-react";
import type { ApprovalItem, CostAnomaly, DeciderResponseTrace, InvestigationReport } from "../types";
import { DecisionPanel } from "./DecisionPanel";
import { InvestigationReportPanel } from "./InvestigationReportPanel";

interface FindingsPageProps {
  anomaly: CostAnomaly | null;
  decision: DeciderResponseTrace | null;
  report: InvestigationReport | null;
  approvals: ApprovalItem[];
  query: string;
  canDownload: boolean;
  onDownloadReport: () => void;
}

export function FindingsPage({ anomaly, decision, report, approvals, query, canDownload, onDownloadReport }: FindingsPageProps) {
  const visibleApprovals = approvals.filter((item) => !query || `${item.service} ${item.environment} ${item.suggested_action} ${item.id}`.toLowerCase().includes(query.toLowerCase()));
  const pending = visibleApprovals.filter((item) => item.status === "pending").length;
  const reviewed = visibleApprovals.filter((item) => item.status !== "pending").length;

  return (
    <main className="page-content findings-page">
      <div className="page-heading-row"><div><p className="eyebrow">ANALYSIS &amp; ANOMALIES</p><h1>Findings <em>&amp; evidence</em></h1><p className="page-lede">Review the latest analyzed signal and its evidence trail. This API does not expose a general findings history yet.</p></div><span className="provenance observed">API-SOURCED RECORDS</span></div>
      <section className="finding-summary-strip" aria-label="Finding and approval summary">
        <div><span className="summary-icon critical-icon"><AlertTriangle size={17} /></span><strong>{anomaly ? 1 : 0}</strong><span>Current analyses</span></div>
        <div><span className="summary-icon pending-icon"><span aria-hidden="true">●</span></span><strong>{pending}</strong><span>Pending approvals</span></div>
        <div><span className="summary-icon resolved-icon"><CheckCircle size={17} /></span><strong>{reviewed}</strong><span>Reviewed approvals</span></div>
        <div className="summary-search"><Search size={15} /><span>{query ? `Filtering approvals by “${query}”` : "Search is available in the header"}</span></div>
      </section>
      {!anomaly ? <section className="empty-state"><span className="eyebrow">NO FINDINGS YET</span><h2>Run an analysis to inspect a signal.</h2><p>Only records returned by the backend will appear here.</p><a className="action-primary" href="#overview">Go to Overview <span aria-hidden="true">→</span></a></section> : <>
        <div className="finding-workspace">
          <aside className="finding-list" aria-label="Current finding">
            <div className="finding-list-head"><span className="eyebrow">LATEST API ANALYSIS</span><strong>1 record</strong></div>
            <article className="finding-row selected">
              <div className="finding-row-tags"><span className={`severity-tag severity-${anomaly.criticality}`}>{anomaly.criticality.toUpperCase()}</span><span className="provenance estimated">{anomaly.is_simulated ? "SYNTHETIC" : "TELEMETRY"}</span></div>
              <h2>{anomaly.scenario_name}</h2><p>{anomaly.service} · {anomaly.environment}</p>
              <div className="finding-row-impact"><strong>{anomaly.currency} {anomaly.metrics.delta_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/day</strong><time>{new Date(anomaly.detected_at).toLocaleString()}</time></div>
              <span className="finding-detail-link">Selected analysis <span aria-hidden="true">→</span></span>
            </article>
            <div className="finding-history-note">Historical findings and resolved/suppressed states are not provided by the current API.</div>
          </aside>
          <section className="finding-detail">
            <div className="detail-breadcrumb"><span>Latest analysis</span><span>/</span><strong>{anomaly.anomaly_id}</strong></div>
            <div className="detail-title-row"><div><span className={`severity-tag severity-${anomaly.criticality}`}>{anomaly.criticality.toUpperCase()} SEVERITY</span><h2>{anomaly.scenario_name}</h2><p>{anomaly.service} · {anomaly.environment} · Detected {new Date(anomaly.detected_at).toLocaleString()}</p></div><span className="detail-delta">{anomaly.currency} {anomaly.metrics.delta_amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}<small>daily delta</small></span></div>
            <div className="evidence-grid"><article><span>BASELINE SPEND</span><strong>{anomaly.currency} {anomaly.metrics.baseline_spend.toLocaleString(undefined, { minimumFractionDigits: 2 })}</strong></article><article><span>OBSERVED SPEND</span><strong>{anomaly.currency} {anomaly.metrics.current_spend.toLocaleString(undefined, { minimumFractionDigits: 2 })}</strong></article><article><span>CHANGE</span><strong>{anomaly.metrics.delta_percentage > 0 ? "+" : ""}{anomaly.metrics.delta_percentage.toFixed(1)}%</strong></article><article><span>CONFIDENCE</span><strong>{decision ? `${(decision.confidence * 100).toFixed(1)}%` : "Not returned"}</strong></article></div>
            <div className="diagnostic-block"><span className="diagnostic-number">01</span><div><h3>What happened?</h3><p>{report?.observed_facts[0] ?? "No explanation was returned by the API."}</p><p>{report?.observed_facts[1] ?? ""}</p></div></div>
            <div className="diagnostic-block"><span className="diagnostic-number amber-number">02</span><div><h3>Financial exposure</h3><p>Projected month-end spend is {anomaly.currency} {anomaly.metrics.forecast_month_end.toLocaleString(undefined, { minimumFractionDigits: 2 })} against a budget of {anomaly.currency} {anomaly.metrics.monthly_budget.toLocaleString(undefined, { minimumFractionDigits: 2 })} ({anomaly.metrics.budget_burn_percentage.toFixed(1)}% burn).</p></div></div>
            <div className="diagnostic-block"><span className="diagnostic-number lime-number">03</span><div><h3>Recommended next step</h3><p>{report?.safe_recommendations[0] ?? "Review the policy decision before making operational changes."}</p><p className="safety-caption">Decision support only. No infrastructure change has been made.</p></div></div>
          </section>
        </div>
        <div className="findings-support-grid">{decision && <DecisionPanel decision={decision} />}{report && <InvestigationReportPanel report={report} canDownload={canDownload} onDownload={onDownloadReport} />}</div>
      </>}
      <section className="ledger-panel findings-approval-panel"><div className="ledger-panel-heading"><div><span className="eyebrow">HUMAN REVIEW</span><h2>Approval records</h2></div><a className="text-link" href="#recommendations">Open approval queue <span aria-hidden="true">→</span></a></div>{visibleApprovals.length ? <ul className="finding-approval-list">{visibleApprovals.slice(0, 8).map((item) => <li key={item.id}><span className={`approval-dot status-${item.status}`} /><span className="approval-service">{item.service}</span><span className="approval-action-text">{item.suggested_action}</span><span className={`provenance ${item.status === "pending" ? "estimated" : "observed"}`}>{item.status.toUpperCase()}</span></li>)}</ul> : <p className="table-empty">{query ? "No approval records match the current filter." : "No approval records have been returned."}</p>}</section>
    </main>
  );
}
