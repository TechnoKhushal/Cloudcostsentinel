import React from "react";
import { Sparkles, FileText, CheckSquare, Search, AlertCircle, Shield } from "lucide-react";
import type { InvestigationReport } from "../types";

interface InvestigationReportPanelProps {
  report: InvestigationReport | null;
  canDownload?: boolean;
  onDownload?: () => void;
}

export const InvestigationReportPanel: React.FC<InvestigationReportPanelProps> = ({ report, canDownload = false, onDownload }) => {
  if (!report) return null;

  return (
    <div className="panel-card">
      <div className="panel-header">
        <h2 className="panel-title">
          <Sparkles size={18} color="#a855f7" />
          <span>{report.provider === "openrouter" ? "AI-assisted Cost Investigation" : "Grounded Cost Investigation · Deterministic"}</span>
        </h2>
        <div style={{ display: "flex", gap: "0.5rem", fontSize: "0.75rem" }}>
          <span className="status-pill pill-purple">
            {report.provider}
          </span>
          <span className="status-pill">
            {report.model_id}
          </span>
          {canDownload && <button type="button" className="btn btn-secondary btn-sm" onClick={onDownload} aria-label="Download this report securely">⇩ Download JSON</button>}
        </div>
      </div>

      {/* Executive Summary */}
      <div className="report-section">
        <div className="report-section-title">
          <FileText size={15} />
          <span>Executive Summary</span>
        </div>
        <p className="report-text">{report.executive_summary}</p>
      </div>

      {/* Observed Facts */}
      <div className="report-section">
        <div className="report-section-title">
          <Search size={15} />
          <span>Observed Telemetry Facts</span>
        </div>
        <ul className="report-list">
          {report.observed_facts.map((fact, idx) => (
            <li key={idx}>{fact}</li>
          ))}
        </ul>
      </div>

      {/* Decider Audit Grounding */}
      <div
        className="report-section"
        style={{
          background: "var(--bg-panel)",
          padding: "0.75rem 1rem",
          borderRadius: "8px",
          borderLeft: "3px solid var(--accent-cyan)",
        }}
      >
        <div className="report-section-title" style={{ color: "var(--accent-cyan)" }}>
          <Shield size={15} />
          <span>Decider Choice Alignment Audit</span>
        </div>
        <p className="report-text" style={{ fontSize: "0.82rem" }}>
          {report.decider_action_audit}
        </p>
      </div>

      {/* Investigation Areas & Recommendations in 2 columns */}
      <div className="report-columns">
        <div className="report-section">
          <div className="report-section-title">
            <AlertCircle size={15} />
            <span>Likely Areas to Investigate</span>
          </div>
          <ul className="report-list">
            {report.likely_investigation_areas.map((area, idx) => (
              <li key={idx}>{area}</li>
            ))}
          </ul>
        </div>

        <div className="report-section">
          <div className="report-section-title">
            <CheckSquare size={15} />
            <span>Safe Recommendations</span>
          </div>
          <ul className="report-list">
            {report.safe_recommendations.map((rec, idx) => (
              <li key={idx}>{rec}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Follow-up Checklist */}
      <div className="report-section" style={{ marginTop: "0.5rem" }}>
        <div className="report-section-title">
          <CheckSquare size={15} />
          <span>Follow-up Checklist</span>
        </div>
        <ul className="report-list">
          {report.follow_up_checklist.map((item, idx) => (
            <li key={idx}>{item}</li>
          ))}
        </ul>
      </div>
    </div>
  );
};
