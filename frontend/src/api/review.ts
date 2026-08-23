import { apiRequest, approverActor, newIdempotencyKey } from "./client";

export type Assignment = {
  assignment_id: string;
  case_id: string;
  document_version_id: string;
  audit_run_id: string;
  baseline_version_id: string;
  queue_code: string;
  assignment_status: string;
  expected_revision: number;
  allowed_actions: string[];
  highest_severity: string;
  risk_count: number;
};

export type ApprovalInput = {
  caseId: string;
  assignmentId: string;
  documentVersionId: string;
  auditRunId: string;
  baselineVersionId: string;
  expectedRevision: number;
  locatorId: string;
  reason: string;
};

export type FindingEditInput = Omit<ApprovalInput, "locatorId"> & { findingId: string };

export const listAssignments = () => apiRequest<Assignment[]>("/api/v1/review-queues/legal_review/assignments?status=queued", { actor: approverActor });

export const getAssignment = (caseId: string, assignmentId: string) => apiRequest<Assignment>(`/api/v1/cases/${caseId}/assignments/${assignmentId}`, {
  actor: approverActor,
});

export const acceptAssignment = (caseId: string, assignmentId: string, expectedRevision: number) => apiRequest<Assignment>(`/api/v1/cases/${caseId}/assignments/${assignmentId}/accept`, {
  method: "POST", actor: approverActor, idempotencyKey: newIdempotencyKey("accept"), body: { expected_revision: expectedRevision, idempotency_key: newIdempotencyKey("accept-payload") },
});

export const editFinding = (input: FindingEditInput) => apiRequest<{ decision_id: string; expected_revision: number }>(`/api/v1/cases/${input.caseId}/assignments/${input.assignmentId}/decisions`, {
  method: "POST",
  actor: approverActor,
  body: {
    action: "edit",
    document_version_id: input.documentVersionId,
    audit_run_id: input.auditRunId,
    baseline_version_id: input.baselineVersionId,
    risk_item_id: input.findingId,
    expected_revision: input.expectedRevision,
    idempotency_key: newIdempotencyKey("edit"),
    reason: input.reason,
    evidence_refs: [],
    payload: { before_value: "high", after_value: "medium" },
  },
});

export const submitApproval = (input: ApprovalInput) => apiRequest<{ decision_id: string; case_status: string; expected_revision: number }>(`/api/v1/cases/${input.caseId}/assignments/${input.assignmentId}/decisions`, {
  method: "POST",
  actor: approverActor,
  body: {
    action: "approve",
    document_version_id: input.documentVersionId,
    audit_run_id: input.auditRunId,
    baseline_version_id: input.baselineVersionId,
    expected_revision: input.expectedRevision,
    idempotency_key: newIdempotencyKey("approve"),
    reason: input.reason,
    evidence_refs: [{ type: "locator", id: input.locatorId }],
    payload: { conditions: [] },
  },
});
