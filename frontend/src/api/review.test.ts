import { afterEach, expect, test, vi } from "vitest";
import { acceptAssignment, editFinding, getAssignment, submitApproval } from "./review";

afterEach(() => vi.restoreAllMocks());

test("uses the case-scoped HITL routes and current context", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ data: { assignment_id: "assignment_1", expected_revision: 2 } }), { headers: { "Content-Type": "application/json" } }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ data: { decision_id: "decision_edit", expected_revision: 3 } }), { headers: { "Content-Type": "application/json" } }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ data: { decision_id: "decision_1", case_status: "approved" } }), { headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);

  await acceptAssignment("case_1", "assignment_1", 1);
  await editFinding({
    caseId: "case_1", assignmentId: "assignment_1", documentVersionId: "docv_1", auditRunId: "run_1", baselineVersionId: "baseline_1", expectedRevision: 2, findingId: "finding_1", reason: "风险项已完成复核",
  });
  await submitApproval({
    caseId: "case_1", assignmentId: "assignment_1", documentVersionId: "docv_1", auditRunId: "run_1", baselineVersionId: "baseline_1", expectedRevision: 3, locatorId: "locator_1", reason: "证据已核验",
  });

  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    "/api/v1/cases/case_1/assignments/assignment_1/accept",
    "/api/v1/cases/case_1/assignments/assignment_1/decisions",
    "/api/v1/cases/case_1/assignments/assignment_1/decisions",
  ]);
  expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toMatchObject({
    action: "edit", risk_item_id: "finding_1", expected_revision: 2,
  });
  expect(JSON.parse(fetchMock.mock.calls[2][1].body as string)).toMatchObject({
    action: "approve", document_version_id: "docv_1", audit_run_id: "run_1", baseline_version_id: "baseline_1", evidence_refs: [{ type: "locator", id: "locator_1" }],
  });
});

test("reads one assignment through the real case-scoped endpoint", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    data: { assignment_id: "assignment_1", case_id: "case_1", expected_revision: 4 },
  }), { headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);

  await expect(getAssignment("case_1", "assignment_1")).resolves.toMatchObject({
    assignment_id: "assignment_1", case_id: "case_1", expected_revision: 4,
  });

  expect(fetchMock).toHaveBeenCalledWith("/api/v1/cases/case_1/assignments/assignment_1", expect.objectContaining({
    headers: expect.objectContaining({ "X-Actor-ID": "frontend-approver", "X-Actor-Role": "approver" }),
  }));
});
