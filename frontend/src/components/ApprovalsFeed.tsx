import { useMemo, useState } from "react";
import { CheckCircle, XCircle, UserCheck } from "lucide-react";
import type { ApprovalItem } from "../types";
import { countApprovals, filterApprovals, type ApprovalFilter } from "../approvalQueue";

interface ApprovalsFeedProps {
  approvals: ApprovalItem[];
  onDecide: (id: string, action: "approved" | "rejected") => void;
  pendingIds?: Set<string>;
  error?: string | null;
}

export const ApprovalsFeed = ({ approvals, onDecide, pendingIds = new Set(), error }: ApprovalsFeedProps) => {
  const [filter, setFilter] = useState<ApprovalFilter>("pending");
  const [search, setSearch] = useState("");
  const counts = useMemo(() => countApprovals(approvals), [approvals]);
  const visibleApprovals = useMemo(() => filterApprovals(approvals, filter, search), [approvals, filter, search]);

  return (
  <section className="panel-card approvals-panel">
    <div className="panel-header"><h2 className="panel-title"><UserCheck size={18} aria-hidden="true" />Approval queue</h2><span className="status-pill">{approvals.filter((item) => item.status === "pending").length} pending</span></div>
    <p className="panel-description">Review decisions recorded by the API. Approving or rejecting updates the audit record only; it never changes cloud resources.</p>
    {error && <p className="inline-error" role="alert">Approval data could not be refreshed: {error}</p>}
    {!error && approvals.length > 0 && <div className="approval-tools">
      <label className="approval-search"><span aria-hidden="true">⌕</span><span className="sr-only">Search approvals</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search service, action, or ID" /></label>
      <div className="approval-filters" role="group" aria-label="Filter approval queue">
        {(["pending", "all", "approved", "rejected"] as const).map((value) => <button key={value} type="button" className={`filter-chip ${filter === value ? "active" : ""}`} aria-pressed={filter === value} onClick={() => setFilter(value)}>{value === "all" ? "All" : value[0].toUpperCase() + value.slice(1)} <span>{counts[value]}</span></button>)}
      </div>
    </div>}
    {!error && approvals.length === 0 ? <div className="empty-copy">No approval items have been recorded.</div>
      : !error && visibleApprovals.length === 0 ? <div className="empty-copy">No {filter === "all" ? "approval" : filter} items match this search.</div>
      : visibleApprovals.map((item) => {
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
