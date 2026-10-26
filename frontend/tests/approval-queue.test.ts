import assert from "node:assert/strict";
import { test } from "node:test";
import { countApprovals, filterApprovals } from "../src/approvalQueue.ts";
import type { ApprovalItem } from "../src/types.ts";

const approvals = [
  { id: "appr-1", service: "Amazon EC2", environment: "prod", suggested_action: "Review scaling", status: "pending" },
  { id: "appr-2", service: "RDS", environment: "staging", suggested_action: "Check storage", status: "approved" },
  { id: "appr-3", service: "Amazon EC2", environment: "prod", suggested_action: "Review capacity", status: "rejected" },
].map((item) => item as ApprovalItem);

test("approval queue counts each review state", () => {
  assert.deepEqual(countApprovals(approvals), { all: 3, pending: 1, approved: 1, rejected: 1 });
});

test("approval filters combine status with case-insensitive search", () => {
  assert.deepEqual(filterApprovals(approvals, "pending", "ec2"), [approvals[0]]);
  assert.deepEqual(filterApprovals(approvals, "all", " APPR-3 "), [approvals[2]]);
  assert.deepEqual(filterApprovals(approvals, "approved", "no match"), []);
});
