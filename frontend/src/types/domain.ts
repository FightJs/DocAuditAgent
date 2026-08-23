export type ApiSuccess<T> = { data: T; request_id?: string };

export type ApiErrorEnvelope = {
  error: { code: string; message: string; details?: Record<string, unknown>; retryable?: boolean; request_id?: string };
};

export class ApiError extends Error {
  readonly code: string;
  readonly details?: Record<string, unknown>;
  readonly requestId?: string;
  readonly retryable: boolean;

  constructor(error: ApiErrorEnvelope["error"]) {
    super(error.message);
    this.name = "ApiError";
    this.code = error.code;
    this.details = error.details;
    this.requestId = error.request_id;
    this.retryable = error.retryable ?? false;
  }
}

export type CaseStatus = "created" | "uploading" | "human_reviewing" | "changes_requested" | "approved" | "rejected" | "delivered";

export type AuditRun = { audit_run_id: string; baseline_version_id: string; status: string; is_current?: boolean };
export type DocumentVersion = { document_version_id: string; version_number: number; status: string; parent_document_version_id?: string | null; is_read_only?: boolean };

export type AuditCase = {
  case_id: string;
  case_reference: string;
  contract_type?: string;
  audit_scope_id: string;
  status: CaseStatus;
  revision: number;
  current_document_version?: DocumentVersion;
  current_audit_run?: AuditRun;
  assignment_summary?: { assignment_id: string; queue_code: string; assignment_status: string; expected_revision?: number };
  allowed_actions: string[];
  created_at?: string;
  updated_at?: string;
};

export type UploadBatch = {
  upload_batch_id: string;
  document_version_id: string;
  revision: number;
  files: { upload_session_id: string; role: string }[];
};

export type AuditSubmission = { case_id: string; document_version_id: string; audit_run_id: string; case_status: CaseStatus };

export type Finding = { finding_id: string; title: string; severity: string; status: string; confidence_band?: string; locator_ids?: string[] };
export type FindingDetail = Finding & { summary: string; source_locator: { locator_id?: string; locator_status: string; quote?: string; context_excerpt?: string; section_path?: string[]; page?: number | null } };
