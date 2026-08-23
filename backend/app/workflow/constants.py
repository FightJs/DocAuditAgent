"""Audit workflow literal constants.

Vocabulary follows `docs/08_api_spec/api_spec-v1.0.md` (lower snake_case) for
identifiers (case_id / document_version_id / audit_run_id / baseline_version_id)
and enum values. All values are plain strings so graph state, interrupt payloads
and resume values stay JSON-serializable, as required by
`docs/06_system_architecture/langchain_hitl_document_audit_arch-v1.0.md` §7.
"""

from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# Audit run status (审核运行状态). Business case status (approved/rejected/...)
# is owned by backend services, never by this graph.
# ---------------------------------------------------------------------------
RUN_STATUS_PREPARING: str = "preparing"
RUN_STATUS_AGENT_REVIEWING: str = "agent_reviewing"
RUN_STATUS_TRIAGED: str = "triaged"
RUN_STATUS_AWAITING_HUMAN: str = "awaiting_human"
RUN_STATUS_COMPLETED: str = "completed"
RUN_STATUS_FAILED: str = "failed"

RunStatus = Literal[
    "preparing",
    "agent_reviewing",
    "triaged",
    "awaiting_human",
    "completed",
    "failed",
]

# ---------------------------------------------------------------------------
# Candidate finding fields (inputs to triage).
# ---------------------------------------------------------------------------
SEVERITY_CRITICAL: str = "critical"
SEVERITY_HIGH: str = "high"
SEVERITY_MEDIUM: str = "medium"
SEVERITY_LOW: str = "low"
SEVERITY_UNKNOWN: str = "unknown"

#: Severities that always force the human path (数据模型 5.3).
SEVERITIES_FORCED_HUMAN: frozenset[str] = frozenset({SEVERITY_CRITICAL, SEVERITY_HIGH})

CONFIDENCE_HIGH: str = "high"
CONFIDENCE_MEDIUM: str = "medium"
CONFIDENCE_LOW: str = "low"
CONFIDENCE_UNKNOWN: str = "unknown"

#: Confidence bands that always force the human path.
CONFIDENCE_FORCED_HUMAN: frozenset[str] = frozenset(
    {CONFIDENCE_LOW, CONFIDENCE_UNKNOWN}
)

HIT_TYPE_RULE_HIT: str = "rule_hit"
HIT_TYPE_LLM_INFERRED: str = "llm_inferred"
HIT_TYPE_CONFLICT: str = "conflict"
HIT_TYPE_EVIDENCE_GAP: str = "evidence_gap"

LOCATOR_STATUS_OK: str = "ok"
LOCATOR_STATUS_APPROXIMATE: str = "approximate"
LOCATOR_STATUS_STALE: str = "stale"
LOCATOR_STATUS_UNAVAILABLE: str = "unavailable"

#: Locator statuses that count as degraded (数据模型 locator 降级规则).
LOCATOR_DEGRADED: frozenset[str] = frozenset(
    {LOCATOR_STATUS_STALE, LOCATOR_STATUS_UNAVAILABLE}
)

RULE_EVAL_PASSED: str = "passed"
RULE_EVAL_INCONCLUSIVE: str = "inconclusive"
RULE_EVAL_FAILED: str = "failed"
RULE_EVAL_SKIPPED: str = "skipped"

#: Rule evaluation statuses that block auto-routing (数据模型 5.3).
RULE_EVAL_FORCED_HUMAN: frozenset[str] = frozenset(
    {RULE_EVAL_INCONCLUSIVE, RULE_EVAL_FAILED, RULE_EVAL_SKIPPED}
)

PARSE_STATUS_READY: str = "ready"

# ---------------------------------------------------------------------------
# Routing reasons (routing_reasons enum, snake_case form of the data-model
# ReviewSession.routing_reasons domain).
# ---------------------------------------------------------------------------
ROUTING_REASON_REDLINE: str = "redline"
ROUTING_REASON_HIGH_SEVERITY: str = "high_severity"
ROUTING_REASON_LOW_CONFIDENCE: str = "low_confidence"
ROUTING_REASON_EVIDENCE_GAP: str = "evidence_gap"
ROUTING_REASON_PARSE_QUALITY: str = "parse_quality"
ROUTING_REASON_RULE_CONFLICT: str = "rule_conflict"
ROUTING_REASON_SUBMITTER_OBJECTION: str = "submitter_objection"
ROUTING_REASON_MANUAL_ROUTE: str = "manual_route"

ROUTING_REASONS_ALL: frozenset[str] = frozenset(
    {
        ROUTING_REASON_REDLINE,
        ROUTING_REASON_HIGH_SEVERITY,
        ROUTING_REASON_LOW_CONFIDENCE,
        ROUTING_REASON_EVIDENCE_GAP,
        ROUTING_REASON_PARSE_QUALITY,
        ROUTING_REASON_RULE_CONFLICT,
        ROUTING_REASON_SUBMITTER_OBJECTION,
        ROUTING_REASON_MANUAL_ROUTE,
    }
)

# ---------------------------------------------------------------------------
# Human decision actions accepted as graph resume values (API 规范 §6.3 的
# 路由相关子集；finding 级 edit/withdraw 等由 services 在暂停期间处理，
# 不作为图恢复路由输入).
# ---------------------------------------------------------------------------
ACTION_APPROVE: str = "approve"
ACTION_REJECT: str = "reject"
ACTION_REQUEST_SUPPLEMENT: str = "request_supplement"
ACTION_TRANSFER: str = "transfer"
ACTION_ESCALATE: str = "escalate"

#: Actions that end the graph run (via the finalize node).
TERMINAL_ACTIONS: frozenset[str] = frozenset(
    {ACTION_APPROVE, ACTION_REJECT, ACTION_REQUEST_SUPPLEMENT}
)

#: Actions that re-route responsibility and re-pause for the next human.
REDIRECT_ACTIONS: frozenset[str] = frozenset({ACTION_TRANSFER, ACTION_ESCALATE})

RESUMABLE_ACTIONS: frozenset[str] = frozenset(TERMINAL_ACTIONS | REDIRECT_ACTIONS)

#: Actions that require a non-empty human reason (数据模型 Decision.reason_text).
ACTIONS_REQUIRING_REASON: frozenset[str] = frozenset(
    {ACTION_REJECT, ACTION_REQUEST_SUPPLEMENT, ACTION_TRANSFER, ACTION_ESCALATE}
)

# ---------------------------------------------------------------------------
# Run outcomes (graph 终态路由结果，供 services 投影业务状态；绝不等于
# 自动批准 —— "approved" 只能由已校验的人工决定 resume 产生).
# ---------------------------------------------------------------------------
OUTCOME_READY_FOR_DELIVERY: str = "ready_for_delivery"
OUTCOME_APPROVED: str = "approved"
OUTCOME_REJECTED: str = "rejected"
OUTCOME_CHANGES_REQUESTED: str = "changes_requested"

OUTCOME_BY_TERMINAL_ACTION: dict[str, str] = {
    ACTION_APPROVE: OUTCOME_APPROVED,
    ACTION_REJECT: OUTCOME_REJECTED,
    ACTION_REQUEST_SUPPLEMENT: OUTCOME_CHANGES_REQUESTED,
}

# ---------------------------------------------------------------------------
# Error codes emitted into state["error"].
# ---------------------------------------------------------------------------
ERROR_PRECONDITION_FAILED: str = "precondition_failed"
ERROR_AGENT_FAILED: str = "agent_failed"
