"""Tests for AuditWorkflowRunner: thread binding, pre-resume validation,
guard hook, and snapshot read-model."""

from __future__ import annotations

import pytest

from app.workflow import constants as c
from app.workflow.runner import (
    AuditWorkflowRunner,
    RunNotFoundError,
    RunNotPausedError,
    ThreadMismatchError,
)
from app.workflow.state import AuditRunInput, CandidateFinding, InvalidResumePayload


class StubReviewer:
    def __init__(self, findings=None):
        self._findings = findings if findings is not None else []

    def review(self, request):
        return list(self._findings)


RISKY = CandidateFinding(
    finding_ref="cand-1",
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


def make_input(run_id: str = "run_01", **overrides) -> AuditRunInput:
    base = AuditRunInput(
        case_id="case_01",
        document_version_id="docv_01",
        audit_run_id=run_id,
        baseline_version_id="baseline_2026_01",
        parse_status=c.PARSE_STATUS_READY,
        parse_quality_ok=True,
        rule_coverage_complete=True,
        parsed_document={"clauses": []},
    )
    base.update(overrides)
    return base


def approve_decision(**overrides) -> dict:
    base = {
        "decision_id": "dec_01",
        "action": c.ACTION_APPROVE,
        "actor_id": "user_01",
        "actor_role": "approver",
        "reason": "all findings reviewed",
    }
    base.update(overrides)
    return base


def test_start_auto_run_completes_without_human():
    runner = AuditWorkflowRunner(reviewer=StubReviewer(findings=[]))
    snap = runner.start(make_input())
    assert snap.thread_id == "run_01"
    assert snap.awaiting_human is False
    assert snap.run_status == c.RUN_STATUS_COMPLETED
    assert snap.outcome == c.OUTCOME_READY_FOR_DELIVERY


def test_start_risky_run_pauses_and_exposes_interrupt_payload():
    runner = AuditWorkflowRunner(reviewer=StubReviewer(findings=[RISKY]))
    snap = runner.start(make_input())
    assert snap.awaiting_human is True
    assert snap.run_status == c.RUN_STATUS_AWAITING_HUMAN
    assert snap.interrupt_payload is not None
    assert snap.interrupt_payload["audit_run_id"] == "run_01"
    assert snap.outcome is None


def test_resume_happy_path_returns_completed_snapshot():
    runner = AuditWorkflowRunner(reviewer=StubReviewer(findings=[RISKY]))
    runner.start(make_input())
    snap = runner.resume("run_01", approve_decision())
    assert snap.awaiting_human is False
    assert snap.outcome == c.OUTCOME_APPROVED
    assert snap.human_decision_count == 1


def test_resume_validates_before_touching_graph():
    """Invalid payloads must not consume the pending interrupt: a subsequent
    valid resume still works."""
    runner = AuditWorkflowRunner(reviewer=StubReviewer(findings=[RISKY]))
    runner.start(make_input())
    with pytest.raises(InvalidResumePayload):
        runner.resume("run_01", {"action": "bogus"})
    with pytest.raises(InvalidResumePayload):
        runner.resume("run_01", approve_decision(action="reject", reason=""))
    snap = runner.resume("run_01", approve_decision())
    assert snap.outcome == c.OUTCOME_APPROVED


def test_resume_requires_paused_run():
    runner = AuditWorkflowRunner(reviewer=StubReviewer(findings=[]))
    runner.start(make_input())
    with pytest.raises(RunNotPausedError):
        runner.resume("run_01", approve_decision())


def test_snapshot_unknown_thread_raises_not_found():
    runner = AuditWorkflowRunner(reviewer=StubReviewer())
    with pytest.raises(RunNotFoundError):
        runner.snapshot("run_missing")


def test_start_requires_audit_run_id():
    runner = AuditWorkflowRunner(reviewer=StubReviewer())
    with pytest.raises(ThreadMismatchError):
        runner.start(make_input(run_id=""))


def test_resume_guard_receives_context_and_can_block():
    calls = []

    def guard(context):
        calls.append(context)
        raise PermissionError("run superseded by docv_02")

    runner = AuditWorkflowRunner(
        reviewer=StubReviewer(findings=[RISKY]), resume_guard=guard
    )
    runner.start(make_input())
    with pytest.raises(PermissionError):
        runner.resume("run_01", approve_decision())
    assert calls[0]["audit_run_id"] == "run_01"
    assert calls[0]["document_version_id"] == "docv_01"
    # guard blocked before resume: still awaiting human
    assert runner.snapshot("run_01").awaiting_human is True


def test_threads_are_isolated_per_audit_run():
    runner = AuditWorkflowRunner(reviewer=StubReviewer(findings=[RISKY]))
    runner.start(make_input("run_a"))
    snap_b = runner.start(make_input("run_b", parse_quality_ok=True))
    assert snap_b.awaiting_human is True
    runner.resume("run_a", approve_decision())
    assert runner.snapshot("run_a").outcome == c.OUTCOME_APPROVED
    assert runner.snapshot("run_b").awaiting_human is True
