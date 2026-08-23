"""API request schemas for cases, uploads, objections and deliveries."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateCaseRequest(StrictModel):
    case_reference: str = Field(min_length=1, max_length=128)
    audit_scope_id: str = Field(min_length=1, max_length=128)
    contract_type: str = Field(min_length=1, max_length=64)
    business_context: dict[str, Any] = Field(default_factory=dict)


class UploadFileDescriptor(StrictModel):
    display_name: str = Field(min_length=1, max_length=255)
    role: Literal["primary_contract", "supporting_attachment"]
    byte_size: int = Field(gt=0, le=50 * 1024 * 1024)
    declared_mime_type: str = Field(min_length=1, max_length=128)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)


class CreateUploadBatchRequest(StrictModel):
    submission_note: str | None = Field(default=None, max_length=2000)
    parent_document_version_id: str | None = None
    files: list[UploadFileDescriptor] = Field(min_length=1, max_length=20)


class SubmitUploadBatchRequest(StrictModel):
    expected_revision: int = Field(ge=1)
    confirm_submission: Literal[True]


class CreateObjectionRequest(StrictModel):
    decision_id: str = Field(min_length=1)
    delivery_id: str | None = None
    document_version_id: str = Field(min_length=1)
    audit_run_id: str = Field(min_length=1)
    baseline_version_id: str = Field(min_length=1)
    objection_type: str = Field(min_length=1)
    scope_type: Literal["case", "risk_items", "delivery"]
    risk_item_ids: list[str] = Field(default_factory=list)
    statement: str = Field(min_length=1, max_length=5000)
    supporting_document_version_ids: list[str] = Field(default_factory=list)


class CreateDeliveryRequest(StrictModel):
    approved_decision_id: str = Field(min_length=1)
    document_version_id: str = Field(min_length=1)
    audit_run_id: str = Field(min_length=1)
    baseline_version_id: str = Field(min_length=1)
    visibility_policy: str = Field(default="submitter_safe")
