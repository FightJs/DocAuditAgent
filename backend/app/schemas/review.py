"""API request schemas for human review assignments and decisions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AcceptAssignmentRequest(StrictModel):
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=256)


class SubmitDecisionRequest(StrictModel):
    action: Literal[
        "approve",
        "edit",
        "reject",
        "request_supplement",
        "transfer",
        "escalate",
        "accept_risk",
        "withdraw",
        "correct",
    ]
    document_version_id: str = Field(min_length=1)
    audit_run_id: str = Field(min_length=1)
    baseline_version_id: str = Field(min_length=1)
    risk_item_id: str | None = None
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=256)
    reason: str | None = Field(default=None, max_length=5000)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    previous_decision_id: str | None = None
