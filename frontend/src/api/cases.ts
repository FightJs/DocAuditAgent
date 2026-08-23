import { apiRequest, newIdempotencyKey, submitterActor, type ApiActor } from "./client";
import type { AuditCase, AuditSubmission, Finding, FindingDetail, UploadBatch } from "../types/domain";

export type CreateCaseInput = {
  case_reference: string;
  audit_scope_id: string;
  contract_type: string;
  business_context: { purpose: string };
};

export const listCases = (status?: string) => apiRequest<AuditCase[]>(`/api/v1/cases${status ? `?status=${status}` : ""}`, { actor: submitterActor });
export const getCase = (caseId: string) => apiRequest<AuditCase>(`/api/v1/cases/${caseId}`, { actor: submitterActor });
export const createCase = (input: CreateCaseInput) => apiRequest<AuditCase>("/api/v1/cases", {
  method: "POST", actor: submitterActor, idempotencyKey: newIdempotencyKey("case"), body: input,
});

export async function submitDocument(input: CreateCaseInput, files: File[]): Promise<AuditSubmission> {
  if (files.length === 0) throw new Error("请至少选择一份合同正文");
  const created = await createCase(input);
  const uploadBatch = await apiRequest<UploadBatch>(`/api/v1/cases/${created.case_id}/upload-batches`, {
    method: "POST",
    actor: submitterActor,
    idempotencyKey: newIdempotencyKey("batch"),
    body: {
      submission_note: "前端提交材料",
      files: files.map((file, index) => ({
        display_name: file.name,
        role: index === 0 ? "primary_contract" : "supporting_attachment",
        byte_size: file.size,
        declared_mime_type: file.type || "application/octet-stream",
      })),
    },
  });
  await Promise.all(uploadBatch.files.map((session, index) => apiRequest(`/api/v1/upload-sessions/${session.upload_session_id}/content`, {
    method: "PUT", actor: submitterActor, rawBody: files[index], headers: { "Content-Type": files[index].type || "application/octet-stream" },
  })));
  return apiRequest<AuditSubmission>(`/api/v1/upload-batches/${uploadBatch.upload_batch_id}/submit`, {
    method: "POST", actor: submitterActor, idempotencyKey: newIdempotencyKey("submit"), body: { expected_revision: uploadBatch.revision, confirm_submission: true },
  });
}

export const listFindings = (caseId: string, auditRunId: string, actor: ApiActor = submitterActor) => apiRequest<Finding[]>(`/api/v1/cases/${caseId}/audit-runs/${auditRunId}/findings`, { actor });
export const getFinding = (caseId: string, auditRunId: string, findingId: string, actor: ApiActor = submitterActor) => apiRequest<FindingDetail>(`/api/v1/cases/${caseId}/audit-runs/${auditRunId}/findings/${findingId}`, { actor });
