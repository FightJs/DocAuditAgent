"""Graph node implementations for the audit workflow.

HITL running constraints honored here (langchain_hitl_document_audit_arch
section 7):

- Side effects before an interrupt must be idempotent: every node update uses
  plain overwrite semantics computed from the checkpointed state, so a node
  re-executing from its start after resume never duplicates anything. The
  graph creates no todos, sends no notifications and writes no decisions;
  those side effects belong to services, which observe state transitions.
- Interrupt signals are never swallowed: `interrupt()` is called outside any
  try/except, and the only broad except (agent_review) wraps a node that
  contains no interrupt.
- Each `human_review` entry issues exactly one interrupt; re-routing
  (transfer/escalate) is expressed by conditional edges back into the node,
  never by an interrupt loop inside a single execution.
- Interrupt payloads are minimal and JSON-serializable: ids, routing reasons
  and finding summaries only. No prompts, model traces or secrets.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from app.workflow import constants as c
from app.workflow.llm import AgentReviewError, AgentReviewer
from app.workflow.state import (
    AuditRunState,
    HumanDecisionInput,
    ReviewRequest,
    validate_resume_payload,
)
from app.workflow.triage import triage_run

NODE_PREPARE = "prepare_run"
NODE_AGENT_REVIEW = "agent_review"
NODE_TRIAGE = "triage"
NODE_HUMAN_REVIEW = "human_review"
NODE_FINALIZE = "finalize"


def prepare_run_node(state: AuditRunState) -> dict[str, Any]:
    """Validate entry conditions (HITL spec 4.1): the document version must
    have passed intake + parsing and the baseline must be fixed."""
    missing = [
        field
        for field in ("case_id", "document_version_id", "audit_run_id", "baseline_version_id")
        if not state.get(field)
    ]
    if missing:
        return {
            "run_status": c.RUN_STATUS_FAILED,
            "error": {
                "code": c.ERROR_PRECONDITION_FAILED,
                "message": f"missing run context fields: {', '.join(missing)}",
            },
        }
    if state.get("parse_status") != c.PARSE_STATUS_READY:
        return {
            "run_status": c.RUN_STATUS_FAILED,
            "error": {
                "code": c.ERROR_PRECONDITION_FAILED,
                "message": (
                    "document version is not parse-ready "
                    f"(parse_status={state.get('parse_status')!r})"
                ),
            },
        }
    return {"run_status": c.RUN_STATUS_AGENT_REVIEWING, "human_decisions": []}


def route_after_prepare(state: AuditRunState) -> str:
    return NODE_AGENT_REVIEW if state.get("run_status") == c.RUN_STATUS_AGENT_REVIEWING else "end"


def make_agent_review_node(reviewer: AgentReviewer):
    """Build the agent_review node bound to a specific reviewer (LLM adapter
    in production, offline stub in tests)."""

    def agent_review_node(state: AuditRunState) -> dict[str, Any]:
        request = ReviewRequest(
            case_id=state["case_id"],
            document_version_id=state["document_version_id"],
            audit_run_id=state["audit_run_id"],
            baseline_version_id=state["baseline_version_id"],
            parsed_document=state.get("parsed_document", {}),
        )
        try:
            findings = reviewer.review(request)
        except AgentReviewError as exc:
            return {
                "run_status": c.RUN_STATUS_FAILED,
                "error": {"code": c.ERROR_AGENT_FAILED, "message": str(exc)[:500]},
            }
        except Exception as exc:  # unexpected reviewer failure; no interrupt here
            return {
                "run_status": c.RUN_STATUS_FAILED,
                "error": {
                    "code": c.ERROR_AGENT_FAILED,
                    "message": f"unexpected reviewer error: {exc}"[:500],
                },
            }
        return {"candidate_findings": findings}

    return agent_review_node


def route_after_agent_review(state: AuditRunState) -> str:
    return NODE_TRIAGE if state.get("run_status") == c.RUN_STATUS_AGENT_REVIEWING else "end"


def triage_node(state: AuditRunState) -> dict[str, Any]:
    """Apply the deterministic forced-human rules and set the route."""
    result = triage_run(
        findings=state.get("candidate_findings", []),
        parse_quality_ok=bool(state.get("parse_quality_ok", False)),
        rule_coverage_complete=bool(state.get("rule_coverage_complete", False)),
    )
    return {
        "run_status": (
            c.RUN_STATUS_AWAITING_HUMAN if result["requires_human"] else c.RUN_STATUS_TRIAGED
        ),
        "requires_human": result["requires_human"],
        "routing_reasons": result["routing_reasons"],
        "routing_details": result["routing_details"],
    }


def route_after_triage(state: AuditRunState) -> str:
    return NODE_HUMAN_REVIEW if state.get("requires_human") else NODE_FINALIZE


def build_interrupt_payload(state: AuditRunState) -> dict[str, Any]:
    """Minimal, JSON-serializable, role-safe interrupt payload (HITL spec 7)."""
    return {
        "kind": "human_review_required",
        "case_id": state["case_id"],
        "document_version_id": state["document_version_id"],
        "audit_run_id": state["audit_run_id"],
        "baseline_version_id": state["baseline_version_id"],
        "routing_reasons": list(state.get("routing_reasons", [])),
        "routing_details": list(state.get("routing_details", [])),
        "finding_count": len(state.get("candidate_findings", [])),
        "findings": [
            {
                "finding_ref": f.get("finding_ref", ""),
                "title": f.get("title", ""),
                "category": f.get("category", ""),
                "severity": f.get("severity", c.SEVERITY_UNKNOWN),
            }
            for f in state.get("candidate_findings", [])
        ],
        "prior_decision_count": len(state.get("human_decisions", [])),
    }


def human_review_node(state: AuditRunState) -> dict[str, Any]:
    """Pause for a human decision, then record the validated resume value.

    Re-executes from the top on resume; both payload construction and the
    append below are computed from checkpointed state, so nothing duplicates.
    Note: a resume value that fails validation here means the runner's
    pre-validation was bypassed - the run must then be treated as failed by
    services, because LangGraph consumes resume values on node failure.
    """
    payload = build_interrupt_payload(state)
    resume_value = interrupt(payload)
    decision = validate_resume_payload(resume_value)

    decisions = list(state.get("human_decisions", []))
    decisions.append(decision)
    update: dict[str, Any] = {
        "human_decisions": decisions,
        "last_decision": decision,
    }
    if decision["action"] in c.REDIRECT_ACTIONS:
        reasons = list(state.get("routing_reasons", []))
        if c.ROUTING_REASON_MANUAL_ROUTE not in reasons:
            reasons.append(c.ROUTING_REASON_MANUAL_ROUTE)
        update["routing_reasons"] = reasons
        update["run_status"] = c.RUN_STATUS_AWAITING_HUMAN
    return update


def route_after_human(state: AuditRunState) -> str:
    last: HumanDecisionInput | None = state.get("last_decision")
    if last and last["action"] in c.REDIRECT_ACTIONS:
        return NODE_HUMAN_REVIEW
    return NODE_FINALIZE


def finalize_node(state: AuditRunState) -> dict[str, Any]:
    """Map the terminal route to a run outcome.

    Without a human decision the outcome is only `ready_for_delivery` - never
    `approved`. `approved`/`rejected`/`changes_requested` outcomes exist only
    as projections of a validated human resume value; the authoritative case
    status transition is performed by services from the persisted Decision.
    """
    last = state.get("last_decision")
    if last is None:
        outcome = c.OUTCOME_READY_FOR_DELIVERY
    else:
        outcome = c.OUTCOME_BY_TERMINAL_ACTION[last["action"]]
    return {"run_status": c.RUN_STATUS_COMPLETED, "outcome": outcome}
