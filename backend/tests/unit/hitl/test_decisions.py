"""人工决定：权限、乐观锁、幂等、append-only、撤回/更正（api_spec 6.3）。"""

import unittest

from tests.unit.hitl import helpers  # noqa: F401 触发 sys.path 引导
from tests.unit.hitl.helpers import (
    APPROVER,
    CONTEXT,
    REVIEWER,
    make_service,
    open_and_accept,
)

from app.hitl import (
    ActionNotAllowedError,
    ActionNotAuthorizedError,
    AssignmentAlreadyTakenError,
    AssignmentStatus,
    DecisionAction,
    DecisionResult,
    DecisionScope,
    EvidenceIncompleteError,
    IdempotencyConflictError,
    InterruptStatus,
    InvalidActionPayloadError,
    RevisionConflictError,
    RunSupersededError,
    ActorRole,
)


def edit_kwargs(assignment, actor=REVIEWER, key="dec-1"):
    return dict(
        assignment_id=assignment.assignment_id,
        action=DecisionAction.EDIT,
        scope=DecisionScope.RISK_ITEM,
        actor_id=actor[0],
        actor_role=actor[1],
        context=CONTEXT,
        expected_revision=assignment.revision,
        idempotency_key=key,
        reason="该条款满足例外条件，调整风险等级",
        risk_item_id="finding_1",
        payload={"before_value": "high", "after_value": "medium"},
    )


class AcceptAssignmentTest(unittest.TestCase):
    def test_revision_conflict(self):
        service, _, _ = make_service()
        from tests.unit.hitl.helpers import open_default_interrupt

        _, assignment, _ = open_default_interrupt(service)
        with self.assertRaises(RevisionConflictError):
            service.accept_assignment(
                assignment_id=assignment.assignment_id,
                actor_id=REVIEWER[0],
                actor_role=REVIEWER[1],
                expected_revision=999,
                idempotency_key="accept-x",
            )

    def test_already_taken_by_other_actor(self):
        service, _, _ = make_service()
        assignment = open_and_accept(service)
        with self.assertRaises(AssignmentAlreadyTakenError):
            service.accept_assignment(
                assignment_id=assignment.assignment_id,
                actor_id="user_other",
                actor_role=ActorRole.REVIEWER,
                expected_revision=assignment.revision,
                idempotency_key="accept-2",
            )

    def test_same_actor_reaccept_is_idempotent(self):
        service, _, _ = make_service()
        assignment = open_and_accept(service)
        again = service.accept_assignment(
            assignment_id=assignment.assignment_id,
            actor_id=REVIEWER[0],
            actor_role=REVIEWER[1],
            expected_revision=assignment.revision,
            idempotency_key="accept-1",
        )
        self.assertEqual(again.assignment_id, assignment.assignment_id)
        self.assertEqual(again.status, AssignmentStatus.ACCEPTED)


class SubmitDecisionTest(unittest.TestCase):
    def test_edit_success_records_decision_and_resumes(self):
        service, _, adapter = make_service()
        assignment = open_and_accept(service)

        outcome = service.submit_decision(**edit_kwargs(assignment))

        self.assertEqual(outcome.decision.result, DecisionResult.ACCEPTED)
        self.assertTrue(outcome.decision.is_current)
        self.assertEqual(outcome.case_status_effect, "human_reviewing")
        self.assertEqual(assignment.status, AssignmentStatus.IN_PROGRESS)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(outcome.resumed_interrupt.status, InterruptStatus.RESUMED)
        self.assertEqual(outcome.resumed_interrupt.decision_id, outcome.decision.decision_id)

    def test_idempotent_replay_returns_same_decision_without_side_effects(self):
        service, _, adapter = make_service()
        assignment = open_and_accept(service)

        first = service.submit_decision(**edit_kwargs(assignment))
        second = service.submit_decision(**edit_kwargs(assignment))

        self.assertEqual(first.decision.decision_id, second.decision.decision_id)
        self.assertEqual(len(service.store.decisions), 1)
        self.assertEqual(len(adapter.calls), 1)  # 重放不再触发恢复

    def test_same_key_different_body_conflicts(self):
        service, _, _ = make_service()
        assignment = open_and_accept(service)
        service.submit_decision(**edit_kwargs(assignment))

        kwargs = edit_kwargs(assignment)
        kwargs["reason"] = "不同的理由"
        with self.assertRaises(IdempotencyConflictError):
            service.submit_decision(**kwargs)

    def test_stale_expected_revision_rejected(self):
        service, _, _ = make_service()
        assignment = open_and_accept(service)
        kwargs = edit_kwargs(assignment)
        kwargs["expected_revision"] = 999
        with self.assertRaises(RevisionConflictError):
            service.submit_decision(**kwargs)

    def test_non_assignee_cannot_submit(self):
        service, _, _ = make_service()
        assignment = open_and_accept(service)
        kwargs = edit_kwargs(assignment, actor=("user_intruder", ActorRole.REVIEWER))
        with self.assertRaises(ActionNotAuthorizedError):
            service.submit_decision(**kwargs)

    def test_reviewer_cannot_approve_case(self):
        service, _, _ = make_service()
        assignment = open_and_accept(service)
        with self.assertRaises(ActionNotAuthorizedError):
            service.submit_decision(
                assignment_id=assignment.assignment_id,
                action=DecisionAction.APPROVE,
                scope=DecisionScope.CASE,
                actor_id=REVIEWER[0],
                actor_role=REVIEWER[1],
                context=CONTEXT,
                expected_revision=assignment.revision,
                idempotency_key="dec-approve",
                reason="同意",
                evidence_refs=[{"type": "rule_hit", "id": "hit_1"}],
            )

    def test_superseded_run_cannot_accept_decision(self):
        service, validator, _ = make_service()
        assignment = open_and_accept(service)
        validator.mark_run_superseded(CONTEXT.audit_run_id)
        with self.assertRaises(RunSupersededError):
            service.submit_decision(**edit_kwargs(assignment))

    def test_approve_blocked_by_pending_risk_items(self):
        service, validator, _ = make_service()
        assignment = open_and_accept(service, actor=APPROVER)
        validator.set_pending_risk_items(CONTEXT.audit_run_id, ["finding_9"])
        with self.assertRaises(ActionNotAllowedError):
            service.submit_decision(
                assignment_id=assignment.assignment_id,
                action=DecisionAction.APPROVE,
                scope=DecisionScope.CASE,
                actor_id=APPROVER[0],
                actor_role=APPROVER[1],
                context=CONTEXT,
                expected_revision=assignment.revision,
                idempotency_key="dec-approve",
                reason="同意",
                evidence_refs=[{"type": "rule_hit", "id": "hit_1"}],
            )

    def test_approve_blocked_by_incomplete_evidence(self):
        service, validator, _ = make_service()
        assignment = open_and_accept(service, actor=APPROVER)
        validator.mark_evidence_incomplete(CONTEXT.audit_run_id)
        with self.assertRaises(EvidenceIncompleteError):
            service.submit_decision(
                assignment_id=assignment.assignment_id,
                action=DecisionAction.APPROVE,
                scope=DecisionScope.CASE,
                actor_id=APPROVER[0],
                actor_role=APPROVER[1],
                context=CONTEXT,
                expected_revision=assignment.revision,
                idempotency_key="dec-approve",
                reason="同意",
                evidence_refs=[{"type": "rule_hit", "id": "hit_1"}],
            )

    def test_approve_success_by_approver(self):
        service, _, _ = make_service()
        assignment = open_and_accept(service, actor=APPROVER)
        outcome = service.submit_decision(
            assignment_id=assignment.assignment_id,
            action=DecisionAction.APPROVE,
            scope=DecisionScope.CASE,
            actor_id=APPROVER[0],
            actor_role=APPROVER[1],
            context=CONTEXT,
            expected_revision=assignment.revision,
            idempotency_key="dec-approve",
            reason="证据完整，同意",
            evidence_refs=[{"type": "rule_hit", "id": "hit_1"}],
        )
        self.assertEqual(outcome.case_status_effect, "approved")
        self.assertEqual(assignment.status, AssignmentStatus.COMPLETED)

    def test_edit_requires_before_and_after(self):
        service, _, _ = make_service()
        assignment = open_and_accept(service)
        kwargs = edit_kwargs(assignment)
        kwargs["payload"] = {"after_value": "low"}
        with self.assertRaises(InvalidActionPayloadError):
            service.submit_decision(**kwargs)

    def test_withdraw_supersedes_previous_decision(self):
        service, _, _ = make_service()
        assignment = open_and_accept(service)
        first = service.submit_decision(**edit_kwargs(assignment, key="dec-1"))

        outcome = service.submit_decision(
            assignment_id=assignment.assignment_id,
            action=DecisionAction.WITHDRAW,
            scope=DecisionScope.RISK_ITEM,
            actor_id=REVIEWER[0],
            actor_role=REVIEWER[1],
            context=CONTEXT,
            expected_revision=assignment.revision,
            idempotency_key="dec-2",
            reason="误操作，撤回",
            risk_item_id="finding_1",
            previous_decision_id=first.decision.decision_id,
        )

        previous = service.store.get_decision(first.decision.decision_id)
        self.assertFalse(previous.is_current)
        self.assertEqual(previous.result, DecisionResult.SUPERSEDED)
        self.assertEqual(outcome.decision.supersedes_decision_id, first.decision.decision_id)
        self.assertEqual(len(service.store.decisions), 2)  # append-only，历史保留

    def test_withdraw_requires_previous_decision(self):
        service, _, _ = make_service()
        assignment = open_and_accept(service)
        with self.assertRaises(InvalidActionPayloadError):
            service.submit_decision(
                assignment_id=assignment.assignment_id,
                action=DecisionAction.WITHDRAW,
                scope=DecisionScope.RISK_ITEM,
                actor_id=REVIEWER[0],
                actor_role=REVIEWER[1],
                context=CONTEXT,
                expected_revision=assignment.revision,
                idempotency_key="dec-w",
                reason="撤回",
                risk_item_id="finding_1",
            )

    def test_transfer_creates_successor_and_supersedes_original(self):
        service, _, _ = make_service()
        assignment = open_and_accept(service)
        outcome = service.submit_decision(
            assignment_id=assignment.assignment_id,
            action=DecisionAction.TRANSFER,
            scope=DecisionScope.CASE,
            actor_id=REVIEWER[0],
            actor_role=REVIEWER[1],
            context=CONTEXT,
            expected_revision=assignment.revision,
            idempotency_key="dec-t",
            reason="超出授权额度，转高级审核",
            payload={
                "target_queue_code": "senior_review",
                "handoff_question": "请确认赔偿上限条款",
            },
        )
        self.assertEqual(assignment.status, AssignmentStatus.SUPERSEDED)
        self.assertIsNotNone(outcome.successor_assignment)
        self.assertEqual(outcome.successor_assignment.queue_code, "senior_review")
        self.assertEqual(outcome.successor_assignment.status, AssignmentStatus.QUEUED)


if __name__ == "__main__":
    unittest.main()
