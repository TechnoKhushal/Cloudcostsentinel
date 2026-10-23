import { CheckCircle, XCircle, UserCheck } from "lucide-react";
import type { ApprovalItem } from "../types";

interface ApprovalsFeedProps {
  approvals: ApprovalItem[];
  onDecide: (id: string, action: "approved" | "rejected") => void;
  pendingIds?: Set<string>;
  error?: string | null;
}

export const ApprovalsFeed = ({ approvals, onDecide, pendingIds = new Set(), error }: ApprovalsFeedProps) => (
  <section className="panel-card approvals-panel">
    <div className="panel-header"><h2 className="panel-title"><UserCheck size={18} aria-hidden="true" />Approval queue</h2><span className="status-pill">{approvals.filter((item) => item.status === "pending").length} pending</span></div>
    <p className="panel-description">Review decisions recorded by the API. Approving or rejecting updates the audit record only; it never changes cloud resources.</p>
    {error && <p className="inline-error" role="alert">Approval data could not be refreshed: {error}</p>}
    {!error && approvals.length === 0 ? <div className="empty-copy">No approval items are currently queued.</div> : approvals.map((item) => {
      const pending = pendingIds.has(item.id);
      return <article key={item.id} className={`approval-item-card ${item.status}`}>
        <div className="approval-details"><div className="approval-heading"><strong>{item.service} <span className="muted">· {item.environment}</span></strong><span className={`approval-status status-${item.status}`}>{item.status}</span></div>
          <p>{item.suggested_action}</p><span className="approval-savings">Estimated monthly savings: ${item.estimated_monthly_savings.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
          {item.reviewed_by && <span className="approval-reviewer">Reviewed by {item.reviewed_by}</span>}
        </div>
        {item.status === "pending" && <div className="approval-actions"><button type="button" className="btn btn-sm btn-approve" onClick={() => onDecide(item.id, "approved")} disabled={pending} aria-label={`Approve ${item.service} item`}>{pending ? "Saving…" : <><CheckCircle size={14} aria-hidden="true" />Approve</>}</button><button type="button" className="btn btn-sm btn-reject" onClick={() => onDecide(item.id, "rejected")} disabled={pending} aria-label={`Reject ${item.service} item`}>{pending ? "Saving…" : <><XCircle size={14} aria-hidden="true" />Reject</>}</button></div>}
      </article>;
    })}
  </section>
);
};
