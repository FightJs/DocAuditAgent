"""Integration seams between API services, HITL decisions and the workflow graph."""

from __future__ import annotations

from datetime import datetime, timezone

from app.hitl.graph import ResumeCommand
from app.hitl.store import InMemoryHitlStore
from app.workflow.runner import AuditWorkflowRunner, RunSnapshot
from app.workflow.state import CandidateFinding, ReviewRequest


_GRAPH_RESUME_ACTIONS = {
    "approve",
    "reject",
    "request_supplement",
}


class OfflineMvpReviewer:
    """Deterministic offline reviewer used by the MVP API service.

    The reviewer intentionally returns one high-severity, well-located candidate
    so every submitted MVP version exercises the mandatory human path. Production
    wiring can replace this with `LLMAgentReviewer` without changing services.
    """

    def review(self, request: ReviewRequest) -> list[CandidateFinding]:
        text = str(request.get("parsed_document", {}).get("text") or "")
        excerpt = text[:160] if text else "合同终止与责任限制条款"
        return [
            CandidateFinding(
                finding_ref="candidate_termination_001",
                category="termination_liability",
                title="终止权与责任限制条款需要人工复核",
                summary="识别到单方终止或责任限制安排，需审核者结合业务上下文确认。",
                severity="high",
                confidence_band="high",
                is_redline=False,
                hit_type="rule_hit",
                locator_ids=["locator_termination_001"],
                locator_status="ok",
                authority_ref_ids=["authority_contract_baseline_001"],
                limitations=[],
                rule_evaluation_status="passed",
                # The quote is materialized into a service-owned locator; the
                # candidate itself remains a minimal graph value.
            )
        ]


class WorkflowGraphAdapter:
    """Bridge HITL `ResumeCommand` to `AuditWorkflowRunner`.

    `HitlService` owns authorization, persistence and audit. This adapter only
    enriches the persisted decision into the workflow resume contract and never
    exposes `thread_id` to API callers.
    """

    def __init__(self, runner: AuditWorkflowRunner, store: InMemoryHitlStore) -> None:
        self._runner = runner
        self._store = store
        self.last_snapshots: dict[str, RunSnapshot] = {}

    def resume(self, thread_id: str, command: ResumeCommand) -> None:
        # Finding projection actions are authoritative business facts but are
        # not graph routing commands. Transfer/escalate are represented by a
        # successor assignment in HITL and likewise keep the graph paused.
        if command.action not in _GRAPH_RESUME_ACTIONS:
            return
        decision = self._store.get_decision(command.decision_id)
        if decision is None:
            raise RuntimeError(f"decision {command.decision_id!r} missing before resume")
        recorded_at = decision.recorded_at or datetime.now(timezone.utc)
        snapshot = self._runner.resume(
            thread_id,
            {
                "decision_id": decision.decision_id,
                "action": decision.action.value,
                "actor_id": decision.actor_id,
                "actor_role": decision.actor_role.value,
                "reason": decision.reason or "",
                "target_queue_code": decision.payload.get("target_queue_code", ""),
                "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
            },
        )
        self.last_snapshots[thread_id] = snapshot
