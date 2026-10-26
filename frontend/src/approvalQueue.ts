import type { ApprovalItem } from "./types";

export type ApprovalFilter = "all" | ApprovalItem["status"];
export type ApprovalCounts = Record<ApprovalFilter, number>;

export function countApprovals(approvals: ApprovalItem[]): ApprovalCounts {
  return {
    all: approvals.length,
    pending: approvals.filter((item) => item.status === "pending").length,
    approved: approvals.filter((item) => item.status === "approved").length,
    rejected: approvals.filter((item) => item.status === "rejected").length,
  };
}

export function filterApprovals(approvals: ApprovalItem[], filter: ApprovalFilter, search: string): ApprovalItem[] {
  const query = search.trim().toLocaleLowerCase();
  return approvals.filter((item) => {
    const matchesFilter = filter === "all" || item.status === filter;
    const searchable = `${item.service} ${item.environment} ${item.suggested_action} ${item.id}`.toLocaleLowerCase();
    return matchesFilter && searchable.includes(query);
  });
}
