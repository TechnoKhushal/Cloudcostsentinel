import React, { useState } from "react";
import {
  Cpu,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Clock,
  ShieldCheck,
  CheckCircle2,
  Mail,
} from "lucide-react";
import type { DeciderResponseTrace } from "../types";

interface DecisionPanelProps {
  decision: DeciderResponseTrace | null;
}

export const DecisionPanel: React.FC<DecisionPanelProps> = ({ decision }) => {
  const [showTrace, setShowTrace] = useState(false);

  if (!decision) return null;

  const actionLabels = {
    monitor: "MONITOR (PASSIVE)",
    notify_owner: "NOTIFY OWNER",
    request_approval: "REQUEST APPROVAL",
  };

  const actionIcons = {
    monitor: <CheckCircle2 size={20} />,
    notify_owner: <Mail size={20} />,
    request_approval: <AlertTriangle size={20} />,
  };

  return (
    <div className="panel-card">
      <div className="panel-header">
        <div className="panel-title">
          <Cpu size={18} color="#06b6d4" />
          <span>Strands Decider 2B — Signature Response</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.75rem" }}>
          <span className="status-pill pill-cyan">
            <Clock size={12} />
            {decision.latency_ms} ms
          </span>
          <span className="status-pill">
            {decision.provider}
          </span>
        </div>
      </div>

      {/* Hero Decision Box */}
      <div className={`decision-hero action-${decision.action}`}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem", marginBottom: "0.75rem" }}>
          <div className={`action-badge-large badge-${decision.action}`}>
            {actionIcons[decision.action]}
            <span>{actionLabels[decision.action]}</span>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Calibrated Confidence</div>
            <div style={{ fontSize: "1.35rem", fontWeight: 700, color: "#fff" }}>
              {(decision.confidence * 100).toFixed(1)}%
            </div>
          </div>
        </div>

        {/* Safety Fallback Alert (if triggered) */}
        {decision.is_fallback && (
          <div
            style={{
              background: "rgba(244, 63, 94, 0.2)",
              border: "1px solid rgba(244, 63, 94, 0.5)",
              padding: "0.6rem 0.85rem",
              borderRadius: "6px",
              fontSize: "0.78rem",
              color: "#fecdd3",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              marginBottom: "0.75rem",
            }}
          >
            <ShieldCheck size={16} />
            <span>
              <strong>Conservative Safety Fallback:</strong> {decision.fallback_reason}
            </span>
          </div>
        )}

        {/* Executed Action Routing Details */}
        <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginTop: "0.5rem" }}>
          <strong>Downstream Execution: </strong>
          <span style={{ fontFamily: "var(--font-mono)", color: "#93c5fd" }}>
            {decision.executed_action}
          </span>
        </div>
      </div>

      {/* Probability Distribution Bar */}
      <div style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.35rem" }}>
          <span>Probability Distribution Across 3 Options:</span>
          <span>N = 3 choices</span>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {Object.entries(decision.probabilities).map(([opt, prob]) => (
            <div key={opt} style={{ flex: 1, background: "var(--bg-subtle)", borderRadius: "6px", padding: "0.5rem" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", textTransform: "capitalize" }}>
                {opt.replace("_", " ")}
              </div>
              <div style={{ fontSize: "0.95rem", fontWeight: 700, color: opt === decision.action ? "#38bdf8" : "#cbd5e1" }}>
                {(prob * 100).toFixed(1)}%
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Collapsible Wire Trace */}
      <div className="trace-accordion">
        <div className="trace-summary" onClick={() => setShowTrace(!showTrace)}>
          <span>Inspect Decider 2B Wire Trace & Normalized State</span>
          {showTrace ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
        {showTrace && (
          <div className="trace-content">
            <div style={{ color: "#38bdf8", marginBottom: "0.35rem" }}>// 1. Exact Typed ChoiceQuestion Spec</div>
            {JSON.stringify(decision.question, null, 2)}

            <div style={{ color: "#38bdf8", margin: "0.75rem 0 0.35rem" }}>// 2. Compact Normalized Input State Sent to Decider</div>
            {decision.normalized_state}

            <div style={{ color: "#38bdf8", margin: "0.75rem 0 0.35rem" }}>// 3. Execution Trace Metadata</div>
            {JSON.stringify(
              {
                decision_id: decision.decision_id,
                model_id: decision.model_id,
                provider: decision.provider,
                latency_ms: decision.latency_ms,
                is_fallback: decision.is_fallback,
                fallback_reason: decision.fallback_reason,
                executed_action: decision.executed_action,
                executed_details: decision.executed_details,
              },
              null,
              2
            )}
          </div>
        )}
      </div>
    </div>
  );
};
