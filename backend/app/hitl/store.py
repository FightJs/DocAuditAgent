"""HITL 内存存储（MVP）。

提供 append-only 决定/审计事实与待办/中断投影的存储抽象。
生产持久化（数据库、LangGraph checkpoint 表）由后续存储实现替换本类，
服务层只依赖本类暴露的方法签名。checkpoint 只恢复图执行，不替代本存储中的
业务决定与审计事件。
"""

from __future__ import annotations

from .enums import AssignmentStatus, InterruptStatus
from .models import AuditEvent, HitlInterrupt, HumanDecision, ReviewAssignment

_ACTIVE_ASSIGNMENT_STATUSES = (
    AssignmentStatus.QUEUED,
    AssignmentStatus.ACCEPTED,
    AssignmentStatus.IN_PROGRESS,
)


class InMemoryHitlStore:
    """线程内单进程存储；幂等键与待办去重键在此建立唯一索引。"""

    def __init__(self) -> None:
        self.assignments: dict[str, ReviewAssignment] = {}
        self.interrupts: dict[str, HitlInterrupt] = {}
        self.decisions: dict[str, HumanDecision] = {}
        self.audit_events: list[AuditEvent] = []
        # (actor_id, assignment_id, action, idempotency_key) -> decision_id
        self._idempotency_index: dict[tuple[str, str, str, str], str] = {}
        # dedup_key -> assignment_id（中断节点重执行的待办去重）
        self._dedup_index: dict[str, str] = {}

    # ---- 待办 ----

    def add_assignment(self, assignment: ReviewAssignment) -> None:
        self.assignments[assignment.assignment_id] = assignment
        if assignment.dedup_key:
            self._dedup_index[assignment.dedup_key] = assignment.assignment_id

    def get_assignment(self, assignment_id: str) -> ReviewAssignment | None:
        return self.assignments.get(assignment_id)

    def find_assignment_by_dedup_key(self, dedup_key: str) -> ReviewAssignment | None:
        assignment_id = self._dedup_index.get(dedup_key)
        return self.assignments.get(assignment_id) if assignment_id else None

    def find_active_assignment_for_run(self, audit_run_id: str) -> ReviewAssignment | None:
        for assignment in self.assignments.values():
            if (
                assignment.context.audit_run_id == audit_run_id
                and assignment.status in _ACTIVE_ASSIGNMENT_STATUSES
            ):
                return assignment
        return None

    # ---- 中断 ----

    def add_interrupt(self, interrupt: HitlInterrupt) -> None:
        self.interrupts[interrupt.interrupt_id] = interrupt

    def get_interrupt(self, interrupt_id: str) -> HitlInterrupt | None:
        return self.interrupts.get(interrupt_id)

    def find_pending_interrupt(
        self, *, thread_id: str | None = None, audit_run_id: str | None = None
    ) -> HitlInterrupt | None:
        for interrupt in self.interrupts.values():
            if interrupt.status is not InterruptStatus.PENDING:
                continue
            if thread_id is not None and interrupt.thread_id != thread_id:
                continue
            if audit_run_id is not None and interrupt.context.audit_run_id != audit_run_id:
                continue
            return interrupt
        return None

    def pending_interrupts_for_run(self, audit_run_id: str) -> list[HitlInterrupt]:
        return [
            i
            for i in self.interrupts.values()
            if i.context.audit_run_id == audit_run_id and i.status is InterruptStatus.PENDING
        ]

    # ---- 决定（append-only）----

    def append_decision(self, decision: HumanDecision) -> None:
        key = (
            decision.actor_id,
            decision.assignment_id,
            decision.action.value,
            decision.idempotency_key,
        )
        self.decisions[decision.decision_id] = decision
        self._idempotency_index[key] = decision.decision_id

    def find_decision_by_idempotency(
        self, actor_id: str, assignment_id: str, action: str, idempotency_key: str
    ) -> HumanDecision | None:
        decision_id = self._idempotency_index.get(
            (actor_id, assignment_id, action, idempotency_key)
        )
        return self.decisions.get(decision_id) if decision_id else None

    def get_decision(self, decision_id: str) -> HumanDecision | None:
        return self.decisions.get(decision_id)

    # ---- 审计事件（append-only）----

    def append_audit_event(self, event: AuditEvent) -> None:
        self.audit_events.append(event)
