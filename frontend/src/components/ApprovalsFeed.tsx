import React from "react";
import { CheckCircle, XCircle, UserCheck } from "lucide-react";
import type { ApprovalItem } from "../types";

interface ApprovalsFeedProps {
  approvals: ApprovalItem[];
  onDecide: (id: string, action: "approved" | "rejected") => void;
}

export const ApprovalsFeed: React.FC<ApprovalsFeedProps> = ({ approvals, onDecide }) => {
  return (
    <div className="panel-card" style={{ marginTop: "1.5rem" }}>
      <div className="panel-header">
        <div className="panel-title">
          <UserCheck size={18} color="#f43f5e" />
          <span>Human-in-the-Loop Approval Queue (Zero Mutative Safety Sandbox)</span>
        </div>
        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
          {approvals.filter((a) => a.status === "pending").length} Pending Actions
        </div>
      </div>

      <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
        Decisions routed as <code style={{ color: "#f43f5e" }}>request_approval</code> escalate to this review queue.
        Approvals record human sign-off in the sentinel audit trail and never trigger unverified cloud deletions.
      </div>

      {approvals.length === 0 ? (
        <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
          No approval items currently queued.
        </div>
      ) : (
        approvals.map((appr) => (
          <div key={appr.id} className={`approval-item-card ${appr.status}`}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                <span style={{ fontWeight: 600, fontSize: "0.88rem", color: "#fff" }}>
                  {appr.service} ({appr.environment})
                </span>
                <span
                  style={{
                    fontSize: "0.7rem",
                    padding: "0.15rem 0.5rem",
                    borderRadius: "4px",
                    textTransform: "uppercase",
                    fontWeight: 700,
                    backgroundColor:
                      appr.status === "approved"
                        ? "rgba(16, 185, 129, 0.2)"
                        : appr.status === "rejected"
                        ? "rgba(239, 68, 68, 0.2)"
                        : "rgba(244, 63, 94, 0.2)",
                    color:
                      appr.status === "approved"
                        ? "#6ee7b7"
                        : appr.status === "rejected"
                        ? "#fca5a5"
                        : "#fecdd3",
                  }}
                >
                  {appr.status}
                </span>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  {appr.id}
                </span>
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                {appr.suggested_action}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#38bdf8", marginTop: "0.2rem" }}>
                Estimated Monthly Savings: ${appr.estimated_monthly_savings.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </div>
            </div>

            <div>
              {appr.status === "pending" ? (
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    className="btn btn-sm btn-approve"
                    onClick={() => onDecide(appr.id, "approved")}
                  >
                    <CheckCircle size={14} />
                    Approve
                  </button>
                  <button
                    className="btn btn-sm btn-reject"
                    onClick={() => onDecide(appr.id, "rejected")}
                  >
                    <XCircle size={14} />
                    Reject
                  </button>
                </div>
              ) : (
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textAlign: "right" }}>
                  <div>Reviewed by: {appr.reviewed_by}</div>
                  <div>Status: {appr.status.toUpperCase()}</div>
                </div>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
};
