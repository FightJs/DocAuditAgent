"""LangGraph state schema and data contracts for the audit workflow.

Everything in this module is plain JSON-serializable data (str / bool / list /
dict / TypedDict). This is a hard requirement from the HITL architecture spec:
interrupt payloads and resume values must be JSON-serializable and minimal, and
checkpointed graph state must not carry secrets, prompts or cross-case data.

Boundary reminder: the graph orchestrates one 审核运行 (audit run) — the
combination of one document version + one fixed baseline. It never writes
business case status, never persists human decisions and never approves
anything on its own; those belong to backend services.
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict

from app.workflow import constants as c


class CandidateFinding(TypedDict, total=False):
    """One agent-produced candidate risk (候选风险项), pre-authoritative.

    Mirrors the fields the triage rules need from the data model
    (`audit_rule_hit_result_model_spec-v1.0.md` §5.3). Authoritative Finding
    records are minted by services; the graph only carries candidates.
    """

    finding_ref: str  # stable candidate reference within this run
    category: str
    title: str
    summary: str
    severity: str  # critical/high/medium/low/unknown
    confidence_band: str  # high/medium/low/unknown
    is_redline: bool
    hit_type: str  # rule_hit/llm_inferred/conflict/evidence_gap
    locator_ids: list[str]
    locator_status: str  # ok/approximate/stale/unavailable
    authority_ref_ids: list[str]
    limitations: list[str]
    rule_evaluation_status: str  # passed/inconclusive/failed/skipped


class ReviewRequest(TypedDict):
    """Input handed to the agent reviewer (LLM adapter or offline stub)."""

    case_id: str
    document_version_id: str
    audit_run_id: str
    baseline_version_id: str
    parsed_document: dict[str, Any]


class HumanDecisionInput(TypedDict, total=False):
    """Resume value contract for the human-review interrupt.

    Services must authorize and persist the authoritative Decision record
    *before* resuming the graph; `decision_id` is the reference to that record.
    The graph only validates shape and routing semantics.
    """

    decision_id: str  # authoritative decision record id (services-owned)
    action: str  # approve/reject/request_supplement/transfer/escalate
    actor_id: str
    actor_role: str
    reason: str
    target_queue_code: str  # required for transfer/escalate
    recorded_at: str  # UTC RFC 3339, services authoritative timestamp


class TriageResult(TypedDict):
    requires_human: bool
    routing_reasons: list[str]  # enum values from constants.ROUTING_REASONS_ALL
    routing_details: list[str]  # free-form human-readable explanations


class WorkflowError(TypedDict):
    code: str
    message: str


class AuditRunInput(TypedDict):
    """Initial graph state for `AuditWorkflowRunner.start`.

    Preconditions (HITL 规范 §4.1): the document version must have passed
    intake and parsing, and the baseline must be fixed before a run starts.
    """

    case_id: str
    document_version_id: str
    audit_run_id: str
    baseline_version_id: str
    parse_status: str  # must be "ready" for the run to proceed
    parse_quality_ok: bool
    rule_coverage_complete: bool
    parsed_document: dict[str, Any]


class AuditRunState(TypedDict, total=False):
    """Internal graph state (checkpointed per audit_run_id thread)."""

    # --- fixed run context (from AuditRunInput, never mutated) ---
    case_id: str
    document_version_id: str
    audit_run_id: str
    baseline_version_id: str
    parse_status: str
    parse_quality_ok: bool
    rule_coverage_complete: bool
    parsed_document: dict[str, Any]

    # --- runtime fields ---
    run_status: str
    candidate_findings: list[CandidateFinding]
    requires_human: bool
    routing_reasons: list[str]
    routing_details: list[str]
    human_decisions: list[HumanDecisionInput]  # append-only within the run
    last_decision: Optional[HumanDecisionInput]
    outcome: str
    error: WorkflowError


class InvalidResumePayload(ValueError):
    """Raised when a resume value does not satisfy HumanDecisionInput."""


def validate_resume_payload(value: Any) -> HumanDecisionInput:
    """Validate a resume value against the HumanDecisionInput contract.

    Called by `AuditWorkflowRunner.resume` *before* invoking the graph, and
    defensively inside the interrupted node. Validation failures must never
    reach the graph in normal operation: a node that raises after
    `interrupt()` has consumed a resume value leaves the run unrecoverable
    (LangGraph replays the consumed value), so callers must treat a raised
    run as failed rather than retrying it.
    """

    if not isinstance(value, dict):
        raise InvalidResumePayload("resume value must be a JSON object")
    action = value.get("action")
    if action not in c.RESUMABLE_ACTIONS:
        raise InvalidResumePayload(
            f"action must be one of {sorted(c.RESUMABLE_ACTIONS)}, got {action!r}"
        )
    for field in ("decision_id", "actor_id", "actor_role"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise InvalidResumePayload(f"{field} is required and must be a string")
    if action in c.ACTIONS_REQUIRING_REASON:
        if not isinstance(value.get("reason"), str) or not value["reason"].strip():
            raise InvalidResumePayload(f"action {action!r} requires a non-empty reason")
    if action in c.REDIRECT_ACTIONS:
        if not isinstance(value.get("target_queue_code"), str) or not value[
            "target_queue_code"
        ]:
            raise InvalidResumePayload(
                f"action {action!r} requires target_queue_code"
            )
    return HumanDecisionInput(
        decision_id=value["decision_id"],
        action=action,
        actor_id=value["actor_id"],
        actor_role=value["actor_role"],
        reason=value.get("reason", ""),
        target_queue_code=value.get("target_queue_code", ""),
        recorded_at=value.get("recorded_at", ""),
    )
