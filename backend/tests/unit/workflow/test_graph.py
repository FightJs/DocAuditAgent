"""Graph-level tests with an offline stub reviewer and InMemorySaver.

Covers the HITL main chain: auto-route to ready_for_delivery, interrupt on
forced-human criteria, resume with each terminal action, transfer/escalate
re-pause semantics, and failure/precondition paths. No network, no real LLM.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.workflow import constants as c
from app.workflow.graph import build_audit_workflow
from app.workflow.state import (
    AuditRunInput,
    CandidateFinding,
    InvalidResumePayload,
    ReviewRequest,
)


class StubReviewer:
    """Offline AgentReviewer stub returning fixed findings or raising."""

    def __init__(self, findings=None, error: Exception | None = None):
        self._findings = findings if findings is not None else []
        self._error = error
        self.calls: list[ReviewRequest] = []

    def review(self, request: ReviewRequest) -> list[CandidateFinding]:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return list(self._findings)


def make_input(**overrides) -> AuditRunInput:
    base = AuditRunInput(
        case_id="case_01",
        document_version_id="docv_01",
        audit_run_id="run_01",
        baseline_version_id="baseline_2026_01",
        parse_status=c.PARSE_STATUS_READY,
        parse_quality_ok=True,
        rule_coverage_complete=True,
        parsed_document={"clauses": [{"clause_id": "1", "text": "..."}]},
    )
    base.update(overrides)
    return base


def risky_finding(**overrides) -> CandidateFinding:
    base = CandidateFinding(
        finding_ref="cand-1",
        category="liability",
        title="unlimited liability",
        summary="no cap present",
        severity=c.SEVERITY_HIGH,
        confidence_band=c.CONFIDENCE_HIGH,
        is_redline=False,
        hit_type=c.HIT_TYPE_RULE_HIT,
        locator_ids=["loc-1"],
        locator_status=c.LOCATOR_STATUS_OK,
        authority_ref_ids=["auth-1"],
        limitations=[],
        rule_evaluation_status=c.RULE_EVAL_PASSED,
    )
    base.update(overrides)
    return base


def decision(action: str, **overrides) -> dict:
    base = {
        "decision_id": f"dec_{action}_01",
        "action": action,
        "actor_id": "user_01",
        "actor_role": "reviewer",
        "reason": "reviewed",
        "recorded_at": "2026-08-15T08:00:00Z",
    }
    base.update(overrides)
    return base


def config(thread_id: str = "run_01") -> dict:
    return {"configurable": {"thread_id": thread_id}}


def build(reviewer):
    return build_audit_workflow(reviewer, checkpointer=InMemorySaver())


# -- happy paths ---------------------------------------------------------


def test_clean_run_goes_straight_to_ready_for_delivery_without_interrupt():
    graph = build(StubReviewer(findings=[]))
    result = graph.invoke(make_input(), config())
    assert "__interrupt__" not in result
    assert result["run_status"] == c.RUN_STATUS_COMPLETED
    assert result["outcome"] == c.OUTCOME_READY_FOR_DELIVERY
    # ready_for_delivery is NOT an approval
    assert result["outcome"] != c.OUTCOME_APPROVED


def test_high_severity_finding_interrupts_with_role_safe_payload():
    graph = build(StubReviewer(findings=[risky_finding()]))
    result = graph.invoke(make_input(), config())
    interrupts = result["__interrupt__"]
    assert len(interrupts) == 1
    payload = interrupts[0].value
    assert payload["kind"] == "human_review_required"
    assert payload["audit_run_id"] == "run_01"
    assert payload["document_version_id"] == "docv_01"
    assert payload["baseline_version_id"] == "baseline_2026_01"
    assert c.ROUTING_REASON_HIGH_SEVERITY in payload["routing_reasons"]
    assert payload["finding_count"] == 1
    # payload minimality: no prompts, no parsed document, no secrets
    assert "parsed_document" not in payload
    assert all(
        key in {"finding_ref", "title", "category", "severity"}
        for f in payload["findings"]
        for key in f
    )
    snap = graph.get_state(config())
    assert snap.values["run_status"] == c.RUN_STATUS_AWAITING_HUMAN
    assert snap.values.get("outcome") is None


def test_resume_approve_completes_with_approved_outcome():
    graph = build(StubReviewer(findings=[risky_finding()]))
    graph.invoke(make_input(), config())
    result = graph.invoke(Command(resume=decision(c.ACTION_APPROVE)), config())
    assert result["run_status"] == c.RUN_STATUS_COMPLETED
    assert result["outcome"] == c.OUTCOME_APPROVED
    assert len(result["human_decisions"]) == 1
    assert result["human_decisions"][0]["decision_id"] == "dec_approve_01"


def test_resume_reject_completes_with_rejected_outcome():
    graph = build(StubReviewer(findings=[risky_finding()]))
    graph.invoke(make_input(), config())
    result = graph.invoke(Command(resume=decision(c.ACTION_REJECT)), config())
    assert result["outcome"] == c.OUTCOME_REJECTED


def test_resume_request_supplement_completes_with_changes_requested():
    graph = build(StubReviewer(findings=[risky_finding()]))
    graph.invoke(make_input(), config())
    result = graph.invoke(
        Command(resume=decision(c.ACTION_REQUEST_SUPPLEMENT)), config()
    )
    assert result["outcome"] == c.OUTCOME_CHANGES_REQUESTED


# -- transfer / escalate re-pause ----------------------------------------


def test_transfer_reinterrupts_then_approve_completes():
    graph = build(StubReviewer(findings=[risky_finding()]))
    graph.invoke(make_input(), config())
    mid = graph.invoke(
        Command(
            resume=decision(
                c.ACTION_TRANSFER,
                reason="not my queue",
                target_queue_code="legal_review",
            )
        ),
        config(),
    )
    # second interrupt: run still awaiting the new responsible party
    assert "__interrupt__" in mid
    assert mid["run_status"] == c.RUN_STATUS_AWAITING_HUMAN
    assert c.ROUTING_REASON_MANUAL_ROUTE in mid["routing_reasons"]
    payload = mid["__interrupt__"][0].value
    assert payload["prior_decision_count"] == 1
    final = graph.invoke(
        Command(resume=decision(c.ACTION_APPROVE, decision_id="dec_approve_02")),
        config(),
    )
    assert final["outcome"] == c.OUTCOME_APPROVED
    assert len(final["human_decisions"]) == 2


def test_escalate_reinterrupts_with_manual_route_reason():
    graph = build(StubReviewer(findings=[risky_finding()]))
    graph.invoke(make_input(), config())
    mid = graph.invoke(
        Command(
            resume=decision(
                c.ACTION_ESCALATE,
                reason="needs expert",
                target_queue_code="escalation",
            )
        ),
        config(),
    )
    assert "__interrupt__" in mid
    assert c.ROUTING_REASON_MANUAL_ROUTE in mid["routing_reasons"]


# -- validation / failure paths ------------------------------------------


def test_invalid_resume_value_raises():
    """The runner pre-validates resume values; this pins the defensive node
    behavior when validation is bypassed (documented poisoned-run semantics:
    LangGraph consumes the resume value on node failure)."""
    graph = build(StubReviewer(findings=[risky_finding()]))
    graph.invoke(make_input(), config())
    with pytest.raises(InvalidResumePayload):
        graph.invoke(Command(resume={"action": "bogus"}), config())


def test_reject_without_reason_is_rejected_by_validation():
    graph = build(StubReviewer(findings=[risky_finding()]))
    graph.invoke(make_input(), config())
    with pytest.raises(InvalidResumePayload):
        graph.invoke(Command(resume=decision(c.ACTION_REJECT, reason="")), config())


def test_transfer_without_target_queue_is_rejected_by_validation():
    graph = build(StubReviewer(findings=[risky_finding()]))
    graph.invoke(make_input(), config())
    with pytest.raises(InvalidResumePayload):
        graph.invoke(
            Command(resume=decision(c.ACTION_TRANSFER, target_queue_code="")),
            config(),
        )


def test_precondition_failure_when_parse_not_ready():
    graph = build(StubReviewer(findings=[risky_finding()]))
    result = graph.invoke(make_input(parse_status="parse_failed"), config())
    assert result["run_status"] == c.RUN_STATUS_FAILED
    assert result["error"]["code"] == c.ERROR_PRECONDITION_FAILED
    assert "__interrupt__" not in result


def test_agent_failure_marks_run_failed_without_interrupt():
    graph = build(StubReviewer(error=RuntimeError("model timeout")))
    result = graph.invoke(make_input(), config())
    assert result["run_status"] == c.RUN_STATUS_FAILED
    assert result["error"]["code"] == c.ERROR_AGENT_FAILED
    assert "__interrupt__" not in result


# -- idempotency / replay constraints ------------------------------------


def test_agent_review_not_rerun_on_resume():
    """Interrupted-node re-execution must not re-run upstream side effects:
    the LLM reviewer is called exactly once across interrupt + resume."""
    reviewer = StubReviewer(findings=[risky_finding()])
    graph = build(reviewer)
    graph.invoke(make_input(), config())
    graph.invoke(Command(resume=decision(c.ACTION_APPROVE)), config())
    assert len(reviewer.calls) == 1


def test_parse_quality_anomaly_interrupts_even_with_zero_findings():
    graph = build(StubReviewer(findings=[]))
    result = graph.invoke(make_input(parse_quality_ok=False), config())
    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert c.ROUTING_REASON_PARSE_QUALITY in payload["routing_reasons"]


def test_incomplete_coverage_interrupts_even_with_zero_findings():
    graph = build(StubReviewer(findings=[]))
    result = graph.invoke(make_input(rule_coverage_complete=False), config())
    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert c.ROUTING_REASON_EVIDENCE_GAP in payload["routing_reasons"]
