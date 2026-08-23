"""Authoritative in-memory API service for the DocAuditAgent MVP.

The service owns business state and projections. It deliberately keeps three
boundaries distinct:

* workflow graph: agent review and run routing for one version+baseline run;
* HITL service: assignments, append-only decisions and controlled resume;
* API service: cases, files, versions, findings, visibility, deliveries and
  business status.

Storage is process-local for the MVP. The public method signatures are shaped
so a transactional database implementation can replace the dictionaries without
changing API contracts.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from app.hitl.enums import (
    ActorRole,
    AssignmentStatus,
    AuditEventType,
    DecisionAction,
    DecisionResult,
    DecisionScope,
    InterruptPoint,
    InterruptStatus,
    Priority,
    RoutingReason,
)
from app.hitl.errors import ActionNotAllowedError, InvalidActionPayloadError
from app.hitl.models import AuditEvent, ContextTriple, HumanDecision, ReviewAssignment
from app.hitl.policies import MvpAuthorizationPolicy
from app.hitl.service import HitlService
from app.hitl.store import InMemoryHitlStore
from app.schemas.common import ActorContext
from app.schemas.cases import (
    CreateCaseRequest,
    CreateDeliveryRequest,
    CreateObjectionRequest,
    CreateUploadBatchRequest,
    SubmitUploadBatchRequest,
)
from app.schemas.review import SubmitDecisionRequest
from app.workflow import constants as workflow_constants
from app.workflow.runner import AuditWorkflowRunner
from app.workflow.state import AuditRunInput

from .errors import (
    ActionNotAllowedServiceError,
    ActionNotAuthorizedServiceError,
    CaseNotFoundError,
    CaseReferenceConflictError,
    IdempotencyConflictServiceError,
    InvalidRequestError,
    ResourceNotFoundError,
    RevisionConflictServiceError,
    UploadIncompleteError,
    UploadSessionConflictError,
    UploadSessionExpiredError,
)
from .models import (
    AuditRunRecord,
    CaseRecord,
    DeliveryRecord,
    DocumentVersionRecord,
    FileAssetRecord,
    FindingRecord,
    IdempotencyRecord,
    LocatorRecord,
    MaterialRequestRecord,
    ObjectionRecord,
    ServiceAuditEventRecord,
    UploadBatchRecord,
    UploadSessionRecord,
)
from .workflow_bridge import OfflineMvpReviewer, WorkflowGraphAdapter


_STAFF_ROLES = {
    ActorRole.REVIEWER,
    ActorRole.EXPERT,
    ActorRole.APPROVER,
    ActorRole.OPERATOR,
    ActorRole.ADMIN,
}
_DECISION_ROLES = {ActorRole.REVIEWER, ActorRole.EXPERT, ActorRole.APPROVER}
_DELIVERY_CREATOR_ROLES = {ActorRole.OPERATOR, ActorRole.ADMIN}
_RESUMABLE_DECISION_ACTIONS = {
    DecisionAction.APPROVE,
    DecisionAction.REJECT,
    DecisionAction.REQUEST_SUPPLEMENT,
    DecisionAction.TRANSFER,
    DecisionAction.ESCALATE,
}
_RESOLVED_FINDING_STATUSES = {
    "accepted_with_authorization",
    "modified",
    "marked_false_positive",
    "superseded",
}
_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class AuditService:
    """Business API facade used by FastAPI routes and offline tests."""

    def __init__(
        self,
        *,
        workflow_runner: AuditWorkflowRunner | None = None,
        reviewer: Any | None = None,
        hitl_store: InMemoryHitlStore | None = None,
    ) -> None:
        self.cases: dict[str, CaseRecord] = {}
        self.document_versions: dict[str, DocumentVersionRecord] = {}
        self.upload_batches: dict[str, UploadBatchRecord] = {}
        self.upload_sessions: dict[str, UploadSessionRecord] = {}
        self.file_assets: dict[str, FileAssetRecord] = {}
        self.audit_runs: dict[str, AuditRunRecord] = {}
        self.findings: dict[str, FindingRecord] = {}
        self.locators: dict[str, LocatorRecord] = {}
        self.material_requests: dict[str, MaterialRequestRecord] = {}
        self.objections: dict[str, ObjectionRecord] = {}
        self.deliveries: dict[str, DeliveryRecord] = {}
        self.timeline_events: list[ServiceAuditEventRecord] = []
        self._case_reference_index: dict[tuple[str, str], str] = {}
        self._idempotency: dict[tuple[str, str, str], IdempotencyRecord] = {}

        self.workflow_runner = workflow_runner or AuditWorkflowRunner(
            reviewer=reviewer or OfflineMvpReviewer()
        )
        self.hitl_store = hitl_store or InMemoryHitlStore()
        self.workflow_adapter = WorkflowGraphAdapter(self.workflow_runner, self.hitl_store)
        self.hitl = HitlService(
            store=self.hitl_store,
            context_validator=self,
            graph_adapter=self.workflow_adapter,
        )
        self.authorization = MvpAuthorizationPolicy()

    # ------------------------------------------------------------------
    # HITL ContextValidator protocol
    # ------------------------------------------------------------------

    def is_current(self, context: ContextTriple) -> bool:
        case = self.cases.get(context.case_id)
        version = self.document_versions.get(context.document_version_id)
        run = self.audit_runs.get(context.audit_run_id)
        return bool(
            case
            and version
            and run
            and case.current_document_version_id == context.document_version_id
            and case.current_audit_run_id == context.audit_run_id
            and version.status == "ready"
            and run.is_current
            and run.baseline_version_id == context.baseline_version_id
        )

    def pending_required_risk_items(self, context: ContextTriple) -> list[str]:
        return [
            finding.finding_id
            for finding in self.findings.values()
            if finding.audit_run_id == context.audit_run_id
            and finding.requires_human_review
            and finding.status not in _RESOLVED_FINDING_STATUSES
        ]

    def evidence_complete(self, context: ContextTriple) -> bool:
        run_findings = [
            finding
            for finding in self.findings.values()
            if finding.audit_run_id == context.audit_run_id
        ]
        for finding in run_findings:
            if not finding.locator_ids:
                return False
            for locator_id in finding.locator_ids:
                locator = self.locators.get(locator_id)
                if locator is None or locator.locator_status in {"stale", "unavailable"}:
                    return False
        return True

    # ------------------------------------------------------------------
    # Cases
    # ------------------------------------------------------------------

    def create_case(
        self, payload: CreateCaseRequest, actor: ActorContext, idempotency_key: str
    ) -> tuple[dict[str, Any], int, bool]:
        self._require_role(actor, {ActorRole.SUBMITTER})
        scope = "POST /api/v1/cases"
        request_data = payload.model_dump(mode="json")
        replay = self._idempotent_replay(scope, actor, idempotency_key, request_data)
        if replay:
            record = self._idempotency[(actor.actor_id, scope, idempotency_key)]
            return dict(record.response), record.status_code, True

        reference_key = (actor.actor_id, payload.case_reference)
        if reference_key in self._case_reference_index:
            raise CaseReferenceConflictError(
                "同一主体的 case_reference 已存在",
                details={"case_reference": payload.case_reference},
            )
        now = _utcnow()
        case = CaseRecord(
            case_id=_new_id("case"),
            case_reference=payload.case_reference,
            audit_scope_id=payload.audit_scope_id,
            contract_type=payload.contract_type,
            business_context=dict(payload.business_context),
            owner_actor_id=actor.actor_id,
            created_at=now,
            updated_at=now,
        )
        self.cases[case.case_id] = case
        self._case_reference_index[reference_key] = case.case_id
        self._append_event(
            case,
            "case_created",
            None,
            case.status,
            "审核案件已创建",
            actor.actor_id,
        )
        response = self._case_created_response(case)
        self._store_idempotency(
            scope, actor, idempotency_key, request_data, response, 201
        )
        return response, 201, False

    def list_cases(self, actor: ActorContext, status: str | None = None) -> list[dict[str, Any]]:
        records = list(self.cases.values())
        if actor.role is ActorRole.SUBMITTER:
            records = [case for case in records if case.owner_actor_id == actor.actor_id]
        elif actor.role not in _STAFF_ROLES:
            records = []
        if status:
            records = [case for case in records if case.status == status]
        records.sort(key=lambda item: item.created_at or _utcnow(), reverse=True)
        return [self._case_response(case, actor) for case in records]

    def get_case(self, case_id: str, actor: ActorContext) -> dict[str, Any]:
        case = self._require_case_access(case_id, actor)
        return self._case_response(case, actor)

    # ------------------------------------------------------------------
    # Uploads and versioned intake
    # ------------------------------------------------------------------

    def create_upload_batch(
        self,
        case_id: str,
        payload: CreateUploadBatchRequest,
        actor: ActorContext,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int, bool]:
        case = self._require_case_access(case_id, actor)
        self._require_case_owner(case, actor)
        scope = f"POST /api/v1/cases/{case_id}/upload-batches"
        request_data = payload.model_dump(mode="json")
        replay = self._idempotent_replay(scope, actor, idempotency_key, request_data)
        if replay:
            record = self._idempotency[(actor.actor_id, scope, idempotency_key)]
            return dict(record.response), record.status_code, True

        primary_count = sum(1 for item in payload.files if item.role == "primary_contract")
        if primary_count != 1:
            raise InvalidRequestError(
                "每个提交版本必须恰好包含一个 primary_contract 文件",
                details={"primary_contract_count": primary_count},
            )
        if payload.parent_document_version_id:
            parent = self.document_versions.get(payload.parent_document_version_id)
            if parent is None or parent.case_id != case_id:
                raise ResourceNotFoundError(
                    "父文档版本不存在或不属于当前案件",
                    details={"parent_document_version_id": payload.parent_document_version_id},
                )
            if case.current_document_version_id != parent.document_version_id:
                raise RevisionConflictServiceError(
                    "只能基于当前有效文档版本创建补件或重提版本",
                    details={"current_document_version_id": case.current_document_version_id},
                )

        now = _utcnow()
        version_number = 1 + max(
            (
                version.version_number
                for version in self.document_versions.values()
                if version.case_id == case_id
            ),
            default=0,
        )
        batch = UploadBatchRecord(
            upload_batch_id=_new_id("batch"),
            case_id=case_id,
            document_version_id=_new_id("docv"),
            submission_note=payload.submission_note,
            created_at=now,
        )
        version = DocumentVersionRecord(
            document_version_id=batch.document_version_id,
            case_id=case_id,
            version_number=version_number,
            parent_document_version_id=payload.parent_document_version_id,
            submission_note=payload.submission_note,
            created_at=now,
        )
        self.upload_batches[batch.upload_batch_id] = batch
        self.document_versions[version.document_version_id] = version

        files: list[dict[str, Any]] = []
        for descriptor in payload.files:
            file_asset = FileAssetRecord(
                file_asset_id=_new_id("file"),
                upload_batch_id=batch.upload_batch_id,
                document_version_id=version.document_version_id,
                display_name=descriptor.display_name,
                role=descriptor.role,
                byte_size=descriptor.byte_size,
                declared_mime_type=descriptor.declared_mime_type,
                declared_sha256=descriptor.sha256,
            )
            session = UploadSessionRecord(
                upload_session_id=_new_id("ups"),
                file_asset_id=file_asset.file_asset_id,
                case_id=case_id,
                expected_byte_size=descriptor.byte_size,
                expires_at=now + timedelta(hours=1),
            )
            self.file_assets[file_asset.file_asset_id] = file_asset
            self.upload_sessions[session.upload_session_id] = session
            version.file_asset_ids.append(file_asset.file_asset_id)
            files.append(
                {
                    "file_asset_id": file_asset.file_asset_id,
                    "role": file_asset.role,
                    "upload_session_id": session.upload_session_id,
                    "status": session.status,
                    "expected_byte_size": session.expected_byte_size,
                    "expires_at": _iso(session.expires_at),
                }
            )

        self._append_event(
            case,
            "upload_batch_created",
            case.status,
            case.status,
            f"上传批次已创建（版本 V{version.version_number}）",
            actor.actor_id,
            document_version_id=version.document_version_id,
        )
        response = {
            "upload_batch_id": batch.upload_batch_id,
            "document_version_id": version.document_version_id,
            "version_number": version.version_number,
            "parent_document_version_id": version.parent_document_version_id,
            "status": version.status,
            "files": files,
            "revision": batch.revision,
        }
        self._store_idempotency(
            scope, actor, idempotency_key, request_data, response, 201
        )
        return response, 201, False

    def upload_content(
        self, upload_session_id: str, content: bytes, actor: ActorContext
    ) -> dict[str, Any]:
        session = self.upload_sessions.get(upload_session_id)
        if session is None:
            raise ResourceNotFoundError(
                "上传会话不存在或不可见", details={"upload_session_id": upload_session_id}
            )
        case = self._require_case_access(session.case_id, actor)
        self._require_case_owner(case, actor)
        file_asset = self.file_assets[session.file_asset_id]
        received_sha = hashlib.sha256(content).hexdigest()

        if session.status == "completed":
            if session.received_sha256 == received_sha:
                return {
                    "upload_session_id": session.upload_session_id,
                    "status": session.status,
                    "received_byte_size": file_asset.received_byte_size,
                    "file_asset_id": file_asset.file_asset_id,
                }
            raise UploadSessionConflictError(
                "同一上传会话不能提交不同内容",
                details={"upload_session_id": upload_session_id},
            )
        if _utcnow() > session.expires_at:
            session.status = "expired"
            raise UploadSessionExpiredError(
                "上传会话已过期", details={"upload_session_id": upload_session_id}
            )
        if len(content) != session.expected_byte_size:
            raise UploadIncompleteError(
                "上传字节数与批次声明不一致",
                details={
                    "expected_byte_size": session.expected_byte_size,
                    "received_byte_size": len(content),
                },
            )
        if file_asset.declared_sha256 and file_asset.declared_sha256 != received_sha:
            raise UploadSessionConflictError(
                "文件内容哈希与批次声明不一致",
                details={"file_asset_id": file_asset.file_asset_id},
            )

        file_asset.content = bytes(content)
        file_asset.received_byte_size = len(content)
        file_asset.actual_sha256 = received_sha
        file_asset.status = "completed"
        session.status = "completed"
        session.received_sha256 = received_sha
        return {
            "upload_session_id": session.upload_session_id,
            "status": session.status,
            "received_byte_size": file_asset.received_byte_size,
            "file_asset_id": file_asset.file_asset_id,
        }

    def submit_upload_batch(
        self,
        upload_batch_id: str,
        payload: SubmitUploadBatchRequest,
        actor: ActorContext,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int, bool]:
        batch = self.upload_batches.get(upload_batch_id)
        if batch is None:
            raise ResourceNotFoundError(
                "上传批次不存在或不可见", details={"upload_batch_id": upload_batch_id}
            )
        case = self._require_case_access(batch.case_id, actor)
        self._require_case_owner(case, actor)
        scope = f"POST /api/v1/upload-batches/{upload_batch_id}/submit"
        request_data = payload.model_dump(mode="json")
        replay = self._idempotent_replay(scope, actor, idempotency_key, request_data)
        if replay:
            record = self._idempotency[(actor.actor_id, scope, idempotency_key)]
            return dict(record.response), record.status_code, True

        if batch.status != "draft":
            raise ActionNotAllowedServiceError(
                "上传批次已提交，不能重复提交不同请求",
                details={"upload_batch_id": upload_batch_id, "status": batch.status},
            )
        if batch.revision != payload.expected_revision:
            raise RevisionConflictServiceError(
                "上传批次已发生变化，请刷新后重试",
                details={
                    "current_revision": batch.revision,
                    "resource_type": "upload_batch",
                    "resource_id": upload_batch_id,
                },
            )
        version = self.document_versions[batch.document_version_id]
        files = [self.file_assets[file_id] for file_id in version.file_asset_ids]
        incomplete = [item.file_asset_id for item in files if item.status != "completed"]
        if incomplete:
            raise UploadIncompleteError(
                "上传批次中仍有文件未提交完整内容",
                details={"incomplete_file_asset_ids": incomplete},
            )

        self._supersede_current_context(case)
        now = _utcnow()
        batch.status = "submitted"
        batch.revision += 1
        batch.submitted_at = now
        version.status = "ready"
        version.is_read_only = False
        version.parse_status = "ready"
        version.parse_quality_status = "ok"
        version.intake_summary = "材料准入与离线解析检查通过"
        version.ready_at = now
        for item in files:
            item.status = "accepted"
        case.status = "uploading"
        case.current_document_version_id = version.document_version_id
        case.revision += 1
        case.updated_at = now
        self._append_event(
            case,
            "state_changed",
            None,
            "uploading",
            "上传批次已提交，材料准入与解析通过",
            actor.actor_id,
            document_version_id=version.document_version_id,
        )

        run = self._start_audit_run(case, version, files)
        response = {
            "case_id": case.case_id,
            "upload_batch_id": batch.upload_batch_id,
            "document_version_id": version.document_version_id,
            "document_version_status": version.status,
            "case_status": case.status,
            "audit_run_id": run.audit_run_id,
            "next_action": "poll_case_status",
        }
        self._store_idempotency(
            scope, actor, idempotency_key, request_data, response, 202
        )
        return response, 202, False

    # ------------------------------------------------------------------
    # Query projections
    # ------------------------------------------------------------------

    def get_timeline(
        self, case_id: str, actor: ActorContext, *, cursor: str | None, limit: int
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self._require_case_access(case_id, actor)
        events: list[dict[str, Any]] = []
        for event in self.timeline_events:
            if event.case_id == case_id:
                events.append(self._timeline_event_response(event))
        for event in self.hitl_store.audit_events:
            if event.context.case_id == case_id:
                events.append(
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type.value,
                        "occurred_at": _iso(event.occurred_at),
                        "document_version_id": event.context.document_version_id,
                        "audit_run_id": event.context.audit_run_id,
                        "prior_state": None,
                        "next_state": None,
                        "summary": event.summary,
                    }
                )
        events.sort(key=lambda item: item["occurred_at"] or "", reverse=True)
        start = int(cursor or 0)
        end = start + min(max(limit, 1), 100)
        page = events[start:end]
        return page, {"next_cursor": str(end) if end < len(events) else None}

    def get_document_version(
        self, case_id: str, document_version_id: str, actor: ActorContext
    ) -> dict[str, Any]:
        self._require_case_access(case_id, actor)
        version = self._require_version(case_id, document_version_id)
        files = [self.file_assets[file_id] for file_id in version.file_asset_ids]
        return {
            "document_version_id": version.document_version_id,
            "case_id": case_id,
            "version_number": version.version_number,
            "status": version.status,
            "parent_document_version_id": version.parent_document_version_id,
            "is_read_only": version.is_read_only,
            "submission_note": version.submission_note,
            "materials": [
                {
                    "file_asset_id": item.file_asset_id,
                    "display_name": item.display_name,
                    "role": item.role,
                    "status": item.status,
                    "byte_size": item.byte_size,
                    "received_byte_size": item.received_byte_size,
                    "declared_mime_type": item.declared_mime_type,
                    "sha256": item.actual_sha256 or item.declared_sha256,
                }
                for item in files
            ],
            "parse_task": {
                "status": version.parse_status,
                "quality_status": version.parse_quality_status,
                "failure_summary": None,
                "retryable": False,
            },
            "intake_summary": version.intake_summary,
            "open_material_requests": [
                request.material_request_id
                for request in self.material_requests.values()
                if request.document_version_id == document_version_id
                and request.status in {"open", "queued"}
            ],
            "created_at": _iso(version.created_at),
            "ready_at": _iso(version.ready_at),
        }

    def list_material_requests(
        self, case_id: str, document_version_id: str, actor: ActorContext
    ) -> list[dict[str, Any]]:
        self._require_case_access(case_id, actor)
        self._require_version(case_id, document_version_id)
        return [
            self._material_request_response(request)
            for request in self.material_requests.values()
            if request.case_id == case_id
            and request.document_version_id == document_version_id
        ]

    def get_audit_run(
        self, case_id: str, audit_run_id: str, actor: ActorContext
    ) -> dict[str, Any]:
        self._require_case_access(case_id, actor)
        run = self._require_run(case_id, audit_run_id)
        return self._run_response(run)

    def get_audit_result(
        self, case_id: str, audit_run_id: str, actor: ActorContext
    ) -> dict[str, Any]:
        self._require_case_access(case_id, actor)
        run = self._require_run(case_id, audit_run_id)
        findings = self._run_findings(run.audit_run_id)
        severity_summary: dict[str, int] = {}
        for finding in findings:
            severity_summary[finding.severity] = severity_summary.get(finding.severity, 0) + 1
        return {
            "audit_run_id": run.audit_run_id,
            "document_version_id": run.document_version_id,
            "baseline_version_id": run.baseline_version_id,
            "result_status": run.result_status,
            "outcome": run.outcome,
            "evaluation_summary": {
                "finding_count": len(findings),
                "pending_count": len(
                    [item for item in findings if item.status not in _RESOLVED_FINDING_STATUSES]
                ),
                "rule_coverage_complete": True,
                "parse_quality_ok": True,
            },
            "severity_summary": severity_summary,
            "review_summary": {
                "requires_human_review": any(item.requires_human_review for item in findings),
                "routing_reasons": list(run.routing_reasons),
                "limitations": [],
            },
            "finding_refs": [item.finding_id for item in findings],
        }

    def list_findings(
        self,
        case_id: str,
        audit_run_id: str,
        actor: ActorContext,
        *,
        status: str | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        self._require_case_access(case_id, actor)
        self._require_run(case_id, audit_run_id)
        findings = self._run_findings(audit_run_id)
        if status:
            findings = [item for item in findings if item.status == status]
        if severity:
            findings = [item for item in findings if item.severity == severity]
        return [self._finding_list_response(item) for item in findings]

    def list_current_case_findings(self, case_id: str, actor: ActorContext) -> list[dict[str, Any]]:
        case = self._require_case_access(case_id, actor)
        if not case.current_audit_run_id:
            return []
        return self.list_findings(case_id, case.current_audit_run_id, actor)

    def get_finding(
        self, case_id: str, audit_run_id: str, finding_id: str, actor: ActorContext
    ) -> dict[str, Any]:
        self._require_case_access(case_id, actor)
        self._require_run(case_id, audit_run_id)
        finding = self._require_finding(case_id, audit_run_id, finding_id)
        locator = self.locators.get(finding.locator_ids[0]) if finding.locator_ids else None
        return {
            **self._finding_list_response(finding),
            "summary": finding.summary,
            "document_version_id": finding.document_version_id,
            "baseline_version_id": finding.baseline_version_id,
            "rule_hit": {
                "rule_hit_id": f"hit_{finding.finding_id}",
                "hit_type": finding.hit_type,
                "evaluation_status": finding.rule_evaluation_status,
            },
            "explanation": {
                "summary": finding.summary,
                "limitations": list(finding.limitations),
            },
            "authority_references": [
                {"authority_ref_id": item, "title": "合同审核基线条款"}
                for item in finding.authority_ref_ids
            ],
            "source_locator": (
                {
                    "locator_id": locator.locator_id,
                    "locator_status": locator.locator_status,
                    "quote": locator.quote,
                    "section_path": locator.section_path,
                    "page": locator.page,
                }
                if locator
                else {"locator_status": "unavailable", "evidence_sufficient": False}
            ),
            "decision_ids": list(finding.decision_ids),
        }

    def get_locator(
        self, case_id: str, audit_run_id: str, locator_id: str, actor: ActorContext
    ) -> dict[str, Any]:
        self._require_case_access(case_id, actor)
        self._require_run(case_id, audit_run_id)
        locator = self.locators.get(locator_id)
        if locator is None or locator.case_id != case_id or locator.audit_run_id != audit_run_id:
            raise ResourceNotFoundError(
                "原文定位不存在或不可见", details={"locator_id": locator_id}
            )
        return {
            "locator_id": locator.locator_id,
            "quote": locator.quote,
            "context_excerpt": locator.context_excerpt,
            "section_path": locator.section_path,
            "page": locator.page,
            "locator_status": locator.locator_status,
            "content_hash": locator.content_hash,
        }

    # ------------------------------------------------------------------
    # Human review
    # ------------------------------------------------------------------

    def list_assignments(
        self, queue_code: str, actor: ActorContext, *, status: str | None = None
    ) -> list[dict[str, Any]]:
        self._require_role(actor, _STAFF_ROLES)
        assignments = [
            item
            for item in self.hitl_store.assignments.values()
            if item.queue_code == queue_code
            and (status is None or item.status.value == status)
        ]
        assignments.sort(key=lambda item: item.created_at or _utcnow())
        return [self._assignment_response(item, actor) for item in assignments]

    def get_assignment(
        self, case_id: str, assignment_id: str, actor: ActorContext
    ) -> dict[str, Any]:
        self._require_case_access(case_id, actor)
        self._require_role(actor, _STAFF_ROLES)
        assignment = self._require_assignment(case_id, assignment_id)
        return self._assignment_response(assignment, actor)

    def accept_assignment(
        self,
        case_id: str,
        assignment_id: str,
        *,
        expected_revision: int,
        idempotency_key: str,
        actor: ActorContext,
    ) -> dict[str, Any]:
        self._require_case_access(case_id, actor)
        self._require_role(actor, _DECISION_ROLES)
        self._require_assignment(case_id, assignment_id)
        scope = f"accept:{assignment_id}"
        request_data = {"expected_revision": expected_revision}
        replay = self._idempotent_replay(scope, actor, idempotency_key, request_data)
        if replay:
            return dict(self._idempotency[(actor.actor_id, scope, idempotency_key)].response)
        assignment = self.hitl.accept_assignment(
            assignment_id=assignment_id,
            actor_id=actor.actor_id,
            actor_role=actor.role,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )
        response = self._assignment_response(assignment, actor)
        self._store_idempotency(scope, actor, idempotency_key, request_data, response, 200)
        return response

    def submit_decision(
        self,
        case_id: str,
        assignment_id: str,
        payload: SubmitDecisionRequest,
        actor: ActorContext,
    ) -> dict[str, Any]:
        case = self._require_case_access(case_id, actor)
        self._require_role(actor, _DECISION_ROLES)
        assignment = self._require_assignment(case_id, assignment_id)
        action = DecisionAction(payload.action)
        context = ContextTriple(
            case_id=case_id,
            document_version_id=payload.document_version_id,
            audit_run_id=payload.audit_run_id,
            baseline_version_id=payload.baseline_version_id,
        )
        scope_value = DecisionScope.RISK_ITEM if payload.risk_item_id else DecisionScope.CASE
        request_data = payload.model_dump(mode="json")
        idem_scope = f"decision:{assignment_id}:{action.value}"
        replay = self._idempotent_replay(
            idem_scope, actor, payload.idempotency_key, request_data
        )
        if replay:
            return dict(
                self._idempotency[
                    (actor.actor_id, idem_scope, payload.idempotency_key)
                ].response
            )

        if payload.risk_item_id:
            self._require_finding(case_id, payload.audit_run_id, payload.risk_item_id)
        for ref in payload.evidence_refs:
            ref_type = ref.get("type")
            ref_id = ref.get("id")
            if ref_type == "locator":
                locator = self.locators.get(ref_id)
                if (
                    locator is None
                    or locator.case_id != case_id
                    or locator.audit_run_id != payload.audit_run_id
                    or locator.document_version_id != payload.document_version_id
                ):
                    raise ResourceNotFoundError("证据定位不存在或不属于当前运行")
            elif ref_type == "rule_hit":
                if not ref_id or not ref_id.startswith("hit_"):
                    raise ResourceNotFoundError("规则命中项不存在或不属于当前运行")
                finding_id = ref_id.removeprefix("hit_")
                self._require_finding(case_id, payload.audit_run_id, finding_id)
            else:
                raise InvalidRequestError("evidence_refs.type 不受支持")
        # Finding-level projection actions must leave the graph interrupt
        # pending. HitlService treats any attached interrupt as consumable, so
        # temporarily detach it for actions outside the graph routing contract.
        interrupt_id = assignment.interrupt_id
        if action not in _RESUMABLE_DECISION_ACTIONS:
            assignment.interrupt_id = None
        try:
            outcome = self.hitl.submit_decision(
                assignment_id=assignment_id,
                action=action,
                scope=scope_value,
                actor_id=actor.actor_id,
                actor_role=actor.role,
                context=context,
                expected_revision=payload.expected_revision,
                idempotency_key=payload.idempotency_key,
                reason=payload.reason,
                evidence_refs=payload.evidence_refs,
                payload=payload.payload,
                risk_item_id=payload.risk_item_id,
                previous_decision_id=payload.previous_decision_id,
            )
        finally:
            assignment.interrupt_id = interrupt_id

        finding_projection: dict[str, Any] | None = None
        if payload.risk_item_id:
            finding = self.findings[payload.risk_item_id]
            finding.decision_ids.append(outcome.decision.decision_id)
            status_by_action = {
                DecisionAction.EDIT: "modified",
                DecisionAction.ACCEPT_RISK: "accepted_with_authorization",
                DecisionAction.WITHDRAW: "pending",
                DecisionAction.CORRECT: "modified",
            }
            finding.status = status_by_action.get(action, finding.status)
            finding_projection = {
                "finding_id": finding.finding_id,
                "status": finding.status,
            }

        if action is DecisionAction.REQUEST_SUPPLEMENT:
            self._create_material_request(case, context, payload.payload)
        if action in {
            DecisionAction.APPROVE,
            DecisionAction.REJECT,
            DecisionAction.REQUEST_SUPPLEMENT,
        }:
            case.status = outcome.case_status_effect
            run = self.audit_runs[context.audit_run_id]
            run.status = "completed"
            run.result_status = outcome.case_status_effect
            run.outcome = outcome.case_status_effect
            run.completed_at = _utcnow()
        else:
            case.status = "human_reviewing"
        case.revision += 1
        case.updated_at = _utcnow()
        audit_event_id = outcome.audit_event_ids[-1] if outcome.audit_event_ids else None
        response = {
            "decision_id": outcome.decision.decision_id,
            "decision_status": outcome.decision.result.value,
            "action": action.value,
            "case_status": case.status,
            "finding_projection": finding_projection,
            "assignment_revision": outcome.assignment.revision,
            "expected_revision": outcome.assignment.revision,
            "audit_event_id": audit_event_id,
            "successor_assignment_id": (
                outcome.successor_assignment.assignment_id
                if outcome.successor_assignment
                else None
            ),
        }
        self._store_idempotency(
            idem_scope, actor, payload.idempotency_key, request_data, response, 201
        )
        return response

    # ------------------------------------------------------------------
    # Objections and deliveries
    # ------------------------------------------------------------------

    def create_objection(
        self,
        case_id: str,
        payload: CreateObjectionRequest,
        actor: ActorContext,
        idempotency_key: str,
    ) -> dict[str, Any]:
        case = self._require_case_access(case_id, actor)
        self._require_case_owner(case, actor)
        self._require_context_ids(
            case, payload.document_version_id, payload.audit_run_id, payload.baseline_version_id
        )
        scope = f"objection:{case_id}"
        request_data = payload.model_dump(mode="json")
        if self._idempotent_replay(scope, actor, idempotency_key, request_data):
            return dict(self._idempotency[(actor.actor_id, scope, idempotency_key)].response)
        now = _utcnow()
        objection = ObjectionRecord(
            objection_id=_new_id("objection"),
            case_id=case_id,
            decision_id=payload.decision_id,
            delivery_id=payload.delivery_id,
            document_version_id=payload.document_version_id,
            audit_run_id=payload.audit_run_id,
            baseline_version_id=payload.baseline_version_id,
            objection_type=payload.objection_type,
            scope_type=payload.scope_type,
            risk_item_ids=list(payload.risk_item_ids),
            statement=payload.statement,
            supporting_document_version_ids=list(payload.supporting_document_version_ids),
            created_at=now,
        )
        self.objections[objection.objection_id] = objection
        response = {
            "objection_id": objection.objection_id,
            "status": objection.status,
            "case_status": case.status,
            "audit_run_id": objection.audit_run_id,
        }
        self._store_idempotency(scope, actor, idempotency_key, request_data, response, 201)
        return response

    def create_delivery(
        self,
        case_id: str,
        payload: CreateDeliveryRequest,
        actor: ActorContext,
        idempotency_key: str,
    ) -> dict[str, Any]:
        case = self._require_case_access(case_id, actor)
        self._require_role(actor, _DELIVERY_CREATOR_ROLES)
        scope = f"delivery:{case_id}"
        request_data = payload.model_dump(mode="json")
        if self._idempotent_replay(scope, actor, idempotency_key, request_data):
            return dict(self._idempotency[(actor.actor_id, scope, idempotency_key)].response)
        self._require_context_ids(
            case, payload.document_version_id, payload.audit_run_id, payload.baseline_version_id
        )
        if case.status != "approved":
            raise ActionNotAllowedServiceError("只有已批准案件可创建交付快照")
        decision = self.hitl_store.get_decision(payload.approved_decision_id)
        if decision is None or decision.action is not DecisionAction.APPROVE:
            raise ActionNotAllowedServiceError("approved_decision_id 不是有效批准决定")
        delivery = DeliveryRecord(
            delivery_id=_new_id("delivery"),
            case_id=case_id,
            approved_decision_id=payload.approved_decision_id,
            document_version_id=payload.document_version_id,
            audit_run_id=payload.audit_run_id,
            baseline_version_id=payload.baseline_version_id,
            delivery_status="delivered",
            visible_result=self.get_audit_result(case_id, payload.audit_run_id, actor),
            visible_conditions=list(decision.payload.get("conditions", [])),
            next_actions=["view_delivery", "submit_objection"],
            created_at=_utcnow(),
        )
        self.deliveries[delivery.delivery_id] = delivery
        case.status = "delivered"
        case.revision += 1
        response = self._delivery_response(delivery)
        self._store_idempotency(scope, actor, idempotency_key, request_data, response, 201)
        return response

    def get_delivery(
        self, case_id: str, delivery_id: str, actor: ActorContext
    ) -> dict[str, Any]:
        self._require_case_access(case_id, actor)
        delivery = self.deliveries.get(delivery_id)
        if delivery is None or delivery.case_id != case_id:
            raise ResourceNotFoundError("交付快照不存在或不可见")
        return self._delivery_response(delivery)

    # ------------------------------------------------------------------
    # Internal authoritative state helpers
    # ------------------------------------------------------------------

    def _start_audit_run(
        self,
        case: CaseRecord,
        version: DocumentVersionRecord,
        files: list[FileAssetRecord],
    ) -> AuditRunRecord:
        run = AuditRunRecord(
            audit_run_id=_new_id("run"),
            case_id=case.case_id,
            document_version_id=version.document_version_id,
            baseline_version_id="baseline_mvp_v1",
            started_at=_utcnow(),
        )
        self.audit_runs[run.audit_run_id] = run
        case.current_audit_run_id = run.audit_run_id
        parsed_text = "\n".join(
            item.content.decode("utf-8", errors="replace") for item in files
        )
        snapshot = self.workflow_runner.start(
            AuditRunInput(
                case_id=case.case_id,
                document_version_id=version.document_version_id,
                audit_run_id=run.audit_run_id,
                baseline_version_id=run.baseline_version_id,
                parse_status="ready",
                parse_quality_ok=True,
                rule_coverage_complete=True,
                parsed_document={"text": parsed_text},
            )
        )
        run.status = snapshot.run_status or "failed"
        run.outcome = snapshot.outcome
        run.routing_reasons = list(snapshot.routing_reasons)
        run.routing_details = list(snapshot.routing_details)
        run.result_status = snapshot.outcome or snapshot.run_status or "failed"
        for candidate in snapshot.values.get("candidate_findings", []):
            locator_id = _new_id("locator")
            finding_id = _new_id("finding")
            quote = parsed_text[:160] or "原文内容不可用"
            self.locators[locator_id] = LocatorRecord(
                locator_id=locator_id,
                case_id=case.case_id,
                document_version_id=version.document_version_id,
                audit_run_id=run.audit_run_id,
                quote=quote,
                context_excerpt=quote,
                section_path=["document"],
                locator_status=candidate.get("locator_status", "unavailable"),
                content_hash=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
                page=1,
            )
            self.findings[finding_id] = FindingRecord(
                finding_id=finding_id,
                case_id=case.case_id,
                document_version_id=version.document_version_id,
                audit_run_id=run.audit_run_id,
                baseline_version_id=run.baseline_version_id,
                category=candidate.get("category", "unknown"),
                title=candidate.get("title", "待确认风险"),
                summary=candidate.get("summary", ""),
                severity=candidate.get("severity", "unknown"),
                confidence_band=candidate.get("confidence_band", "unknown"),
                requires_human_review=snapshot.requires_human,
                is_redline=bool(candidate.get("is_redline", False)),
                locator_ids=[locator_id],
                authority_ref_ids=list(candidate.get("authority_ref_ids", [])),
                rule_evaluation_status=candidate.get("rule_evaluation_status", "inconclusive"),
                hit_type=candidate.get("hit_type", "rule_hit"),
                limitations=list(candidate.get("limitations", [])),
            )
        if snapshot.awaiting_human:
            reasons = [
                RoutingReason(value)
                for value in snapshot.routing_reasons
                if value in {item.value for item in RoutingReason}
            ] or [RoutingReason.MANUAL_ROUTE]
            self.hitl.open_interrupt(
                point=InterruptPoint.RISK_TRIAGE,
                thread_id=run.audit_run_id,
                context=ContextTriple(
                    case_id=case.case_id,
                    document_version_id=version.document_version_id,
                    audit_run_id=run.audit_run_id,
                    baseline_version_id=run.baseline_version_id,
                ),
                routing_reasons=reasons,
                queue_code="legal_review",
                payload=snapshot.interrupt_payload or {},
                priority=(
                    Priority.HIGH
                    if "high_severity" in snapshot.routing_reasons
                    else Priority.NORMAL
                ),
            )
            case.status = "human_reviewing"
        else:
            case.status = "ready_for_delivery"
            run.completed_at = _utcnow()
        case.revision += 1
        case.updated_at = _utcnow()
        return run

    def _supersede_current_context(self, case: CaseRecord) -> None:
        if case.current_document_version_id:
            old_version = self.document_versions[case.current_document_version_id]
            old_version.is_read_only = True
        if case.current_audit_run_id:
            old_run = self.audit_runs[case.current_audit_run_id]
            old_run.is_current = False
            old_run.is_read_only = True
            old_run.result_status = "superseded"
            self.hitl.invalidate_run(
                audit_run_id=old_run.audit_run_id,
                reason="new_document_version",
            )

    def _require_case_access(self, case_id: str, actor: ActorContext) -> CaseRecord:
        case = self.cases.get(case_id)
        if case is None:
            raise CaseNotFoundError("案件不存在或不可见", details={"case_id": case_id})
        if actor.role is ActorRole.SUBMITTER and case.owner_actor_id != actor.actor_id:
            raise CaseNotFoundError("案件不存在或不可见", details={"case_id": case_id})
        if actor.role not in _STAFF_ROLES | {ActorRole.SUBMITTER}:
            raise ActionNotAuthorizedServiceError("当前主体无案件访问权限")
        return case

    @staticmethod
    def _require_case_owner(case: CaseRecord, actor: ActorContext) -> None:
        if actor.role is not ActorRole.SUBMITTER or case.owner_actor_id != actor.actor_id:
            raise ActionNotAuthorizedServiceError("只有案件提交者可执行该动作")

    @staticmethod
    def _require_role(actor: ActorContext, roles: set[ActorRole]) -> None:
        if actor.role not in roles:
            raise ActionNotAuthorizedServiceError("当前角色无权执行该动作")

    def _require_version(self, case_id: str, version_id: str) -> DocumentVersionRecord:
        version = self.document_versions.get(version_id)
        if version is None or version.case_id != case_id:
            raise ResourceNotFoundError("文档版本不存在或不可见")
        return version

    def _require_run(self, case_id: str, run_id: str) -> AuditRunRecord:
        run = self.audit_runs.get(run_id)
        if run is None or run.case_id != case_id:
            raise ResourceNotFoundError("审核运行不存在或不可见")
        return run

    def _require_finding(
        self, case_id: str, run_id: str, finding_id: str
    ) -> FindingRecord:
        finding = self.findings.get(finding_id)
        if (
            finding is None
            or finding.case_id != case_id
            or finding.audit_run_id != run_id
        ):
            raise ResourceNotFoundError("风险项不存在或不可见")
        return finding

    def _require_assignment(
        self, case_id: str, assignment_id: str
    ) -> ReviewAssignment:
        assignment = self.hitl_store.get_assignment(assignment_id)
        if assignment is None or assignment.context.case_id != case_id:
            raise ResourceNotFoundError("人工待办不存在或不可见")
        return assignment

    def _require_context_ids(
        self, case: CaseRecord, version_id: str, run_id: str, baseline_id: str
    ) -> None:
        run = self._require_run(case.case_id, run_id)
        if (
            case.current_document_version_id != version_id
            or case.current_audit_run_id != run_id
            or run.document_version_id != version_id
            or run.baseline_version_id != baseline_id
            or not run.is_current
        ):
            raise RevisionConflictServiceError("版本、运行与基线上下文不一致")

    def _idempotent_replay(
        self, scope: str, actor: ActorContext, key: str, payload: Any
    ) -> bool:
        if not key:
            raise InvalidRequestError("Idempotency-Key 必填")
        record = self._idempotency.get((actor.actor_id, scope, key))
        if record is None:
            return False
        if record.request_fingerprint != _fingerprint(payload):
            raise IdempotencyConflictServiceError("相同幂等键提交了不同请求")
        return True

    def _store_idempotency(
        self,
        scope: str,
        actor: ActorContext,
        key: str,
        payload: Any,
        response: dict[str, Any],
        status_code: int,
    ) -> None:
        self._idempotency[(actor.actor_id, scope, key)] = IdempotencyRecord(
            key=key,
            actor_id=actor.actor_id,
            scope=scope,
            request_fingerprint=_fingerprint(payload),
            response=dict(response),
            status_code=status_code,
        )

    def _append_event(
        self,
        case: CaseRecord,
        event_type: str,
        prior_state: str | None,
        next_state: str | None,
        summary: str,
        actor_id: str | None,
        *,
        document_version_id: str | None = None,
        audit_run_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.timeline_events.append(
            ServiceAuditEventRecord(
                event_id=_new_id("evt"),
                case_id=case.case_id,
                event_type=event_type,
                occurred_at=_utcnow(),
                document_version_id=document_version_id,
                audit_run_id=audit_run_id,
                prior_state=prior_state,
                next_state=next_state,
                summary=summary,
                actor_id=actor_id,
                details=details or {},
            )
        )

    def _case_created_response(self, case: CaseRecord) -> dict[str, Any]:
        return {
            "case_id": case.case_id,
            "case_reference": case.case_reference,
            "status": case.status,
            "audit_scope_id": case.audit_scope_id,
            "revision": case.revision,
            "created_at": _iso(case.created_at),
            "allowed_actions": ["create_upload_batch"],
        }

    def _case_response(self, case: CaseRecord, actor: ActorContext) -> dict[str, Any]:
        version = (
            self.document_versions.get(case.current_document_version_id)
            if case.current_document_version_id
            else None
        )
        run = self.audit_runs.get(case.current_audit_run_id) if case.current_audit_run_id else None
        assignment = (
            self.hitl_store.find_active_assignment_for_run(run.audit_run_id) if run else None
        )
        return {
            "case_id": case.case_id,
            "case_reference": case.case_reference,
            "contract_type": case.contract_type,
            "audit_scope_id": case.audit_scope_id,
            "status": case.status,
            "current_document_version": (
                {
                    "document_version_id": version.document_version_id,
                    "version_number": version.version_number,
                    "status": version.status,
                    "parent_document_version_id": version.parent_document_version_id,
                    "is_read_only": version.is_read_only,
                }
                if version
                else None
            ),
            "current_audit_run": self._run_response(run) if run else None,
            "assignment_summary": (
                {
                    "assignment_id": assignment.assignment_id,
                    "queue_code": assignment.queue_code,
                    "assignment_status": assignment.status.value,
                    "assignee_display": "当前审核者" if assignment.assignee_id else None,
                }
                if assignment
                else None
            ),
            "allowed_actions": self._case_allowed_actions(case, actor),
            "revision": case.revision,
            "updated_at": _iso(case.updated_at),
        }

    @staticmethod
    def _case_allowed_actions(case: CaseRecord, actor: ActorContext) -> list[str]:
        if actor.role is ActorRole.SUBMITTER:
            return ["create_upload_batch", "view_result"]
        if actor.role in _DECISION_ROLES and case.status == "human_reviewing":
            return ["view_findings", "submit_decision"]
        return ["view_result"]

    @staticmethod
    def _run_response(run: AuditRunRecord | None) -> dict[str, Any]:
        if run is None:
            return {}
        return {
            "audit_run_id": run.audit_run_id,
            "document_version_id": run.document_version_id,
            "baseline_version_id": run.baseline_version_id,
            "status": run.status,
            "is_current": run.is_current,
            "is_read_only": run.is_read_only,
            "result_status": run.result_status,
            "outcome": run.outcome,
            "routing_reasons": list(run.routing_reasons),
            "routing_details": list(run.routing_details),
            "started_at": _iso(run.started_at),
            "completed_at": _iso(run.completed_at),
        }

    def _assignment_response(
        self, assignment: ReviewAssignment, actor: ActorContext
    ) -> dict[str, Any]:
        run_findings = self._run_findings(assignment.context.audit_run_id)
        highest = max(
            (item.severity for item in run_findings),
            key=lambda value: _SEVERITY_RANK.get(value, 0),
            default="unknown",
        )
        allowed = []
        if actor.role in _DECISION_ROLES:
            if assignment.status is AssignmentStatus.QUEUED:
                allowed = ["accept"]
            elif assignment.assignee_id == actor.actor_id and assignment.is_active:
                allowed = [item.value for item in self.authorization.allowed_actions(actor.role, DecisionScope.CASE)]
                allowed += [item.value for item in self.authorization.allowed_actions(actor.role, DecisionScope.RISK_ITEM)]
                allowed = sorted(set(allowed))
        return {
            "assignment_id": assignment.assignment_id,
            "case_id": assignment.context.case_id,
            "document_version_id": assignment.context.document_version_id,
            "audit_run_id": assignment.context.audit_run_id,
            "baseline_version_id": assignment.context.baseline_version_id,
            "queue_code": assignment.queue_code,
            "assignment_status": assignment.status.value,
            "assignee_id": assignment.assignee_id,
            "routing_reasons": [item.value for item in assignment.routing_reasons],
            "priority": assignment.priority.value,
            "highest_severity": highest,
            "risk_count": len(run_findings),
            "expected_revision": assignment.revision,
            "allowed_actions": allowed,
            "created_at": _iso(assignment.created_at),
        }

    def _run_findings(self, run_id: str) -> list[FindingRecord]:
        return [item for item in self.findings.values() if item.audit_run_id == run_id]

    @staticmethod
    def _finding_list_response(finding: FindingRecord) -> dict[str, Any]:
        return {
            "finding_id": finding.finding_id,
            "category": finding.category,
            "title": finding.title,
            "severity": finding.severity,
            "confidence": finding.confidence_band,
            "status": finding.status,
            "requires_human_review": finding.requires_human_review,
            "is_redline": finding.is_redline,
            "locator_status": "available" if finding.locator_ids else "unavailable",
            "suggested_actions": ["edit", "accept_risk"],
        }

    @staticmethod
    def _timeline_event_response(event: ServiceAuditEventRecord) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "occurred_at": _iso(event.occurred_at),
            "document_version_id": event.document_version_id,
            "audit_run_id": event.audit_run_id,
            "prior_state": event.prior_state,
            "next_state": event.next_state,
            "summary": event.summary,
        }

    @staticmethod
    def _material_request_response(request: MaterialRequestRecord) -> dict[str, Any]:
        return {
            "material_request_id": request.material_request_id,
            "status": request.status,
            "missing_items": request.missing_items,
            "purpose": request.purpose,
            "related_finding_ids": request.related_finding_ids,
            "due_at": _iso(request.due_at),
            "response_document_version_id": request.response_document_version_id,
        }

    def _create_material_request(
        self, case: CaseRecord, context: ContextTriple, payload: dict[str, Any]
    ) -> MaterialRequestRecord:
        supplements = list(payload.get("requested_supplements", []))
        record = MaterialRequestRecord(
            material_request_id=_new_id("material_request"),
            case_id=case.case_id,
            document_version_id=context.document_version_id,
            audit_run_id=context.audit_run_id,
            status="open",
            missing_items=supplements,
            purpose=str(payload.get("purpose") or "补充审核材料"),
            related_finding_ids=list(payload.get("related_finding_ids", [])),
            created_at=_utcnow(),
        )
        self.material_requests[record.material_request_id] = record
        return record

    @staticmethod
    def _delivery_response(delivery: DeliveryRecord) -> dict[str, Any]:
        return {
            "delivery_id": delivery.delivery_id,
            "approved_decision_id": delivery.approved_decision_id,
            "document_version_id": delivery.document_version_id,
            "audit_run_id": delivery.audit_run_id,
            "baseline_version_id": delivery.baseline_version_id,
            "delivery_status": delivery.delivery_status,
            "visible_result": delivery.visible_result,
            "visible_conditions": delivery.visible_conditions,
            "next_actions": delivery.next_actions,
            "delivered_at": _iso(delivery.created_at),
            "superseded_by_delivery_id": delivery.superseded_by_delivery_id,
        }
