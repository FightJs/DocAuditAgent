"""In-memory business aggregates for the API MVP.

These records are service-owned projections. They are deliberately separate
from workflow graph state and HITL assignment state so that graph checkpoints
never become the authority for cases, files, findings, deliveries or audit
history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CaseRecord:
    case_id: str
    case_reference: str
    audit_scope_id: str
    contract_type: str
    business_context: dict[str, Any]
    owner_actor_id: str
    status: str = "created"
    revision: int = 1
    current_document_version_id: str | None = None
    current_audit_run_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class FileAssetRecord:
    file_asset_id: str
    upload_batch_id: str
    document_version_id: str
    display_name: str
    role: str
    byte_size: int
    declared_mime_type: str
    declared_sha256: str | None = None
    status: str = "created"
    received_byte_size: int = 0
    actual_sha256: str | None = None
    content: bytes = b""


@dataclass
class UploadSessionRecord:
    upload_session_id: str
    file_asset_id: str
    case_id: str
    expected_byte_size: int
    expires_at: datetime
    status: str = "created"
    received_sha256: str | None = None


@dataclass
class UploadBatchRecord:
    upload_batch_id: str
    case_id: str
    document_version_id: str
    submission_note: str | None
    status: str = "draft"
    revision: int = 1
    created_at: datetime | None = None
    submitted_at: datetime | None = None


@dataclass
class DocumentVersionRecord:
    document_version_id: str
    case_id: str
    version_number: int
    parent_document_version_id: str | None
    submission_note: str | None
    status: str = "draft"
    is_read_only: bool = False
    file_asset_ids: list[str] = field(default_factory=list)
    parse_status: str = "not_started"
    parse_quality_status: str = "not_evaluated"
    intake_summary: str | None = None
    created_at: datetime | None = None
    ready_at: datetime | None = None


@dataclass
class AuditRunRecord:
    audit_run_id: str
    case_id: str
    document_version_id: str
    baseline_version_id: str
    status: str = "preparing"
    is_current: bool = True
    is_read_only: bool = False
    result_status: str = "pending"
    outcome: str | None = None
    routing_reasons: list[str] = field(default_factory=list)
    routing_details: list[str] = field(default_factory=list)
    exception_summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class LocatorRecord:
    locator_id: str
    case_id: str
    document_version_id: str
    audit_run_id: str
    quote: str
    context_excerpt: str
    section_path: list[str]
    locator_status: str = "ok"
    content_hash: str = ""
    page: int | None = None


@dataclass
class FindingRecord:
    finding_id: str
    case_id: str
    document_version_id: str
    audit_run_id: str
    baseline_version_id: str
    category: str
    title: str
    summary: str
    severity: str
    confidence_band: str
    status: str = "pending"
    requires_human_review: bool = True
    is_redline: bool = False
    locator_ids: list[str] = field(default_factory=list)
    authority_ref_ids: list[str] = field(default_factory=list)
    rule_evaluation_status: str = "passed"
    hit_type: str = "rule_hit"
    limitations: list[str] = field(default_factory=list)
    decision_ids: list[str] = field(default_factory=list)


@dataclass
class MaterialRequestRecord:
    material_request_id: str
    case_id: str
    document_version_id: str
    audit_run_id: str
    status: str
    missing_items: list[dict[str, Any]]
    purpose: str
    related_finding_ids: list[str] = field(default_factory=list)
    due_at: datetime | None = None
    response_document_version_id: str | None = None
    created_at: datetime | None = None


@dataclass
class ObjectionRecord:
    objection_id: str
    case_id: str
    decision_id: str
    delivery_id: str | None
    document_version_id: str
    audit_run_id: str
    baseline_version_id: str
    objection_type: str
    scope_type: str
    risk_item_ids: list[str]
    statement: str
    supporting_document_version_ids: list[str]
    status: str = "queued"
    created_at: datetime | None = None


@dataclass
class DeliveryRecord:
    delivery_id: str
    case_id: str
    approved_decision_id: str
    document_version_id: str
    audit_run_id: str
    baseline_version_id: str
    delivery_status: str
    visible_result: dict[str, Any]
    visible_conditions: list[str]
    next_actions: list[str]
    created_at: datetime | None = None
    superseded_by_delivery_id: str | None = None


@dataclass
class ServiceAuditEventRecord:
    event_id: str
    case_id: str
    event_type: str
    occurred_at: datetime
    document_version_id: str | None
    audit_run_id: str | None
    prior_state: str | None
    next_state: str | None
    summary: str
    actor_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class IdempotencyRecord:
    key: str
    actor_id: str
    scope: str
    request_fingerprint: str
    response: dict[str, Any]
    status_code: int
