"""HITL 领域服务：中断开启、待办认领、人工决定与受控恢复。

核心不变量（依据见各方法 docstring）：
1. 恢复边界 = 文档版本 + 审核基线 + 审核运行；旧上下文不可恢复。
2. 中断节点重执行不得重复创建待办/通知/决定（dedup_key + 幂等键）。
3. 决定 append-only；先落库、写审计、更新投影，再恢复图执行。
4. `approved` 只由授权人工在有效上下文形成；Agent 完成不等于批准。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from .enums import (
    ActorRole,
    AssignmentStatus,
    AuditEventType,
    DecisionAction,
    DecisionResult,
    DecisionScope,
    InterruptPoint,
    InterruptStatus,
    Priority,
    RoutingReason,
)
from .errors import (
    ActionNotAllowedError,
    ActionNotAuthorizedError,
    AssignmentAlreadyTakenError,
    AssignmentNotFoundError,
    EvidenceIncompleteError,
    IdempotencyConflictError,
    InvalidActionPayloadError,
    RevisionConflictError,
    RunSupersededError,
    StaleHumanTaskError,
)
from .graph import GraphResumeAdapter, ResumeCommand, ensure_json_serializable
from .models import (
    AuditEvent,
    ContextTriple,
    DecisionOutcome,
    HitlInterrupt,
    HumanDecision,
    ReviewAssignment,
)
from .policies import AuthorizationPolicy, ContextValidator, MvpAuthorizationPolicy
from .store import InMemoryHitlStore

# 各动作对 decision_scope 的限制（api_spec 6.3：approve/reject 仅案件级，
# accept_risk 仅风险项级）。
_CASE_ONLY_ACTIONS = {DecisionAction.APPROVE, DecisionAction.REJECT}
_RISK_ITEM_ONLY_ACTIONS = {DecisionAction.ACCEPT_RISK}
# 必须携带理由的动作（数据模型 1.2 reason_text 约束）。
_REASON_REQUIRED_ACTIONS = {
    DecisionAction.REJECT,
    DecisionAction.EDIT,
    DecisionAction.REQUEST_SUPPLEMENT,
    DecisionAction.TRANSFER,
    DecisionAction.ESCALATE,
    DecisionAction.WITHDRAW,
    DecisionAction.CORRECT,
    DecisionAction.ACCEPT_RISK,
}

# 决定受理后建议的案件状态效果（由 services 层最终裁决）。
_CASE_STATUS_EFFECT = {
    DecisionAction.APPROVE: "approved",
    DecisionAction.REJECT: "rejected",
    DecisionAction.REQUEST_SUPPLEMENT: "changes_requested",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def _fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


class HitlService:
    """HITL 领域服务入口。依赖全部注入，便于测试与后续存储/SDK 替换。"""

    def __init__(
        self,
        *,
        store: InMemoryHitlStore | None = None,
        context_validator: ContextValidator,
        graph_adapter: GraphResumeAdapter,
        authorization_policy: AuthorizationPolicy | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._store = store or InMemoryHitlStore()
        self._validator = context_validator
        self._graph = graph_adapter
        self._authz = authorization_policy or MvpAuthorizationPolicy()
        self._clock = clock

    @property
    def store(self) -> InMemoryHitlStore:
        return self._store

    # ------------------------------------------------------------------
    # 中断开启（中断节点内调用；必须幂等，支持恢复后从节点开头重执行）
    # ------------------------------------------------------------------

    def open_interrupt(
        self,
        *,
        point: InterruptPoint,
        thread_id: str,
        context: ContextTriple,
        routing_reasons: list[RoutingReason],
        queue_code: str,
        payload: dict[str, Any],
        priority: Priority = Priority.NORMAL,
        expires_at: datetime | None = None,
    ) -> tuple[HitlInterrupt, ReviewAssignment, bool]:
        """开启 HITL 中断并生成对应人工待办。

        返回 (interrupt, assignment, created)。以 dedup_key = f"{thread_id}:{point}"
        去重：恢复后节点从开头重执行再次调用时，返回既有中断与待办（created=False），
        不重复建单（hitl arch 7：副作用幂等、待办去重）。

        payload 必须为面向人工界面的最小必要、JSON 可序列化摘要；不得携带密钥、
        内部提示词或未授权的跨案件内容。
        """
        ensure_json_serializable(payload, what="中断 payload")
        dedup_key = f"{thread_id}:{point.value}"
        existing = self._store.find_assignment_by_dedup_key(dedup_key)
        if existing is not None:
            interrupt = (
                self._store.get_interrupt(existing.interrupt_id)
                if existing.interrupt_id
                else None
            )
            if interrupt is not None:
                return interrupt, existing, False

        active = self._store.find_active_assignment_for_run(context.audit_run_id)
        if active is not None:
            raise ActionNotAllowedError(
                "同一审核运行已存在活跃人工待办，请先完成或转交",
                details={"assignment_id": active.assignment_id},
            )

        now = self._clock()
        interrupt = HitlInterrupt(
            interrupt_id=_new_id("int"),
            thread_id=thread_id,
            point=point,
            context=context,
            payload=payload,
            created_at=now,
        )
        assignment = ReviewAssignment(
            assignment_id=_new_id("assignment"),
            context=context,
            queue_code=queue_code,
            routing_reasons=list(routing_reasons),
            priority=priority,
            interrupt_id=interrupt.interrupt_id,
            dedup_key=dedup_key,
            created_at=now,
            expires_at=expires_at,
        )
        self._store.add_interrupt(interrupt)
        self._store.add_assignment(assignment)
        self._audit(
            AuditEventType.INTERRUPT_OPENED,
            context,
            actor_id=None,
            summary=f"HITL 中断开启：{point.value}",
            details={
                "interrupt_id": interrupt.interrupt_id,
                "thread_id": thread_id,
                "assignment_id": assignment.assignment_id,
                "queue_code": queue_code,
                "routing_reasons": [r.value for r in routing_reasons],
            },
        )
        return interrupt, assignment, True

    # ------------------------------------------------------------------
    # 待办认领
    # ------------------------------------------------------------------

    def accept_assignment(
        self,
        *,
        assignment_id: str,
        actor_id: str,
        actor_role: ActorRole,
        expected_revision: int,
        idempotency_key: str,
    ) -> ReviewAssignment:
        """接收待办：更新责任，不代表任何风险确认或案件批准（api_spec 6.2）。"""

        assignment = self._require_assignment(assignment_id)
        self._require_active(assignment)

        if assignment.status is not AssignmentStatus.QUEUED:
            if (
                assignment.assignee_id == actor_id
                and assignment.status in (AssignmentStatus.ACCEPTED, AssignmentStatus.IN_PROGRESS)
            ):
                # 同一人重复认领：幂等返回当前状态
                return assignment
            raise AssignmentAlreadyTakenError(
                "待办已被他人认领",
                details={"assignment_id": assignment_id},
            )
        if assignment.revision != expected_revision:
            raise RevisionConflictError(
                "待办已发生变化，请刷新后重试",
                details={
                    "current_revision": assignment.revision,
                    "resource_type": "review_assignment",
                    "resource_id": assignment_id,
                },
            )

        assignment.assignee_id = actor_id
        assignment.assignee_role = actor_role
        assignment.status = AssignmentStatus.ACCEPTED
        assignment.revision += 1
        self._audit(
            AuditEventType.ASSIGNMENT_ACCEPTED,
            assignment.context,
            actor_id=actor_id,
            summary="待办已认领",
            details={"assignment_id": assignment_id, "idempotency_key": idempotency_key},
        )
        return assignment

    # ------------------------------------------------------------------
    # 人工决定（统一入口）+ 受控恢复
    # ------------------------------------------------------------------

    def submit_decision(
        self,
        *,
        assignment_id: str,
        action: DecisionAction,
        scope: DecisionScope,
        actor_id: str,
        actor_role: ActorRole,
        context: ContextTriple,
        expected_revision: int,
        idempotency_key: str,
        reason: str | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        payload: dict[str, Any] | None = None,
        risk_item_id: str | None = None,
        previous_decision_id: str | None = None,
        submitted_at: datetime | None = None,
    ) -> DecisionOutcome:
        """提交人工决定：校验 → append 决定与审计 → 更新投影 → 恢复图执行。

        顺序遵循 api_spec 6.4：决定成功落库、生成审计事件和更新投影之后，
        才按当前有效上下文恢复图执行。任何校验失败都不产生副作用。
        """

        assignment = self._require_assignment(assignment_id)
        payload = payload or {}
        evidence_refs = evidence_refs or []
        ensure_json_serializable(payload, what="决定 payload")
        ensure_json_serializable(evidence_refs, what="证据引用")

        # ---- 幂等重放：同键同请求返回原决定，同键不同请求即冲突 ----
        request_fp = _fingerprint(
            {
                "scope": scope.value,
                "risk_item_id": risk_item_id,
                "reason": reason,
                "evidence_refs": evidence_refs,
                "payload": payload,
                "previous_decision_id": previous_decision_id,
            }
        )
        replayed = self._store.find_decision_by_idempotency(
            actor_id, assignment_id, action.value, idempotency_key
        )
        if replayed is not None:
            if replayed.request_fingerprint != request_fp:
                raise IdempotencyConflictError(
                    "相同幂等键提交了不同的请求内容",
                    details={"decision_id": replayed.decision_id},
                )
            return self._outcome_for_replay(replayed, assignment)

        # ---- 业务校验（恢复前置条件 hitl arch 6.2 在决定入口同样成立）----
        self._require_active(assignment)
        self._require_assignee(assignment, actor_id)
        self._require_context(assignment, context)
        self._require_authorized(actor_role, action, scope)
        self._require_action_payload(
            action=action,
            scope=scope,
            reason=reason,
            payload=payload,
            risk_item_id=risk_item_id,
            previous_decision_id=previous_decision_id,
        )
        if assignment.revision != expected_revision:
            raise RevisionConflictError(
                "待办已发生变化，请刷新后重试",
                details={
                    "current_revision": assignment.revision,
                    "resource_type": "review_assignment",
                    "resource_id": assignment_id,
                },
            )
        if action is DecisionAction.APPROVE:
            self._require_approvable(context, evidence_refs)

        # ---- withdraw/correct：受控撤回/更正，历史决定只读保留 ----
        supersedes_decision_id: str | None = None
        if action in (DecisionAction.WITHDRAW, DecisionAction.CORRECT):
            previous = self._store.get_decision(previous_decision_id or "")
            if previous is None or not previous.is_current:
                raise ActionNotAllowedError(
                    "被撤回/更正的决定不存在或已非当前有效决定",
                    details={"previous_decision_id": previous_decision_id},
                )
            previous.is_current = False
            previous.result = DecisionResult.SUPERSEDED
            supersedes_decision_id = previous.decision_id
            self._audit(
                AuditEventType.DECISION_SUPERSEDED,
                context,
                actor_id=actor_id,
                summary=f"决定被{action.value}取代",
                details={"superseded_decision_id": previous.decision_id},
            )

        # ---- append 决定与审计 ----
        now = self._clock()
        decision = HumanDecision(
            decision_id=_new_id("decision"),
            assignment_id=assignment_id,
            context=context,
            scope=scope,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
            evidence_refs=list(evidence_refs),
            payload=dict(payload),
            idempotency_key=idempotency_key,
            request_fingerprint=request_fp,
            risk_item_id=risk_item_id,
            previous_decision_id=previous_decision_id,
            supersedes_decision_id=supersedes_decision_id,
            interrupt_id=assignment.interrupt_id,
            submitted_at=submitted_at or now,
            recorded_at=now,
        )
        self._store.append_decision(decision)
        assignment.revision += 1
        decision_event = self._audit(
            AuditEventType.DECISION_RECORDED,
            context,
            actor_id=actor_id,
            summary=f"人工决定已记录：{action.value}",
            details={
                "decision_id": decision.decision_id,
                "scope": scope.value,
                "risk_item_id": risk_item_id,
                "assignment_revision": assignment.revision,
            },
        )

        # ---- 投影更新：转交/升级先建后继待办，原待办 superseded ----
        successor = self._apply_assignment_projection(assignment, action, payload)

        # ---- 受控恢复图执行（落库与审计之后）----
        resumed = self._resume_interrupt(assignment, decision, action, reason, payload)

        return DecisionOutcome(
            decision=decision,
            case_status_effect=_CASE_STATUS_EFFECT.get(action, "human_reviewing"),
            assignment=assignment,
            successor_assignment=successor,
            resumed_interrupt=resumed,
            audit_event_ids=[decision_event.event_id],
        )

    # ------------------------------------------------------------------
    # 运行失效：版本/基线变化后旧暂停流程不可恢复（hitl arch 6.3）
    # ------------------------------------------------------------------

    def invalidate_run(self, *, audit_run_id: str, reason: str, actor_id: str | None = None) -> None:
        """将某审核运行下的待处理中断与活跃待办置为失效/被替代。

        旧版本、旧运行、旧 checkpoint 对应历史只读保留；本方法不删除任何记录。
        """
        for interrupt in self._store.pending_interrupts_for_run(audit_run_id):
            interrupt.status = InterruptStatus.INVALIDATED
            interrupt.resolved_at = self._clock()
            self._audit(
                AuditEventType.INTERRUPT_INVALIDATED,
                interrupt.context,
                actor_id=actor_id,
                summary=f"中断失效：{reason}",
                details={"interrupt_id": interrupt.interrupt_id},
            )
        for assignment in list(self._store.assignments.values()):
            if assignment.context.audit_run_id == audit_run_id and assignment.is_active:
                assignment.status = AssignmentStatus.SUPERSEDED
                assignment.closed_at = self._clock()
                assignment.revision += 1
                self._audit(
                    AuditEventType.ASSIGNMENT_SUPERSEDED,
                    assignment.context,
                    actor_id=actor_id,
                    summary=f"待办被替代：{reason}",
                    details={"assignment_id": assignment.assignment_id},
                )

    # ------------------------------------------------------------------
    # 内部：校验与恢复
    # ------------------------------------------------------------------

    def _require_assignment(self, assignment_id: str) -> ReviewAssignment:
        assignment = self._store.get_assignment(assignment_id)
        if assignment is None:
            raise AssignmentNotFoundError(
                "待办不存在或不可见", details={"assignment_id": assignment_id}
            )
        return assignment

    def _require_active(self, assignment: ReviewAssignment) -> None:
        if not assignment.is_active:
            raise StaleHumanTaskError(
                "人工待办已过期、被替代或已完成，请重新查询当前上下文",
                details={
                    "assignment_id": assignment.assignment_id,
                    "assignment_status": assignment.status.value,
                },
            )

    def _require_assignee(self, assignment: ReviewAssignment, actor_id: str) -> None:
        if assignment.assignee_id is None:
            raise ActionNotAllowedError(
                "待办尚未认领，请先接收待办",
                details={"assignment_id": assignment.assignment_id},
            )
        if assignment.assignee_id != actor_id:
            raise ActionNotAuthorizedError(
                "只有当前责任人可提交决定",
                details={"assignment_id": assignment.assignment_id},
            )

    def _require_context(self, assignment: ReviewAssignment, context: ContextTriple) -> None:
        if assignment.context != context:
            raise StaleHumanTaskError(
                "决定上下文与待办绑定的版本/运行/基线不一致",
                details={"assignment_id": assignment.assignment_id},
            )
        if not self._validator.is_current(context):
            raise RunSupersededError(
                "文档版本、审核基线或审核运行已被替代，旧流程不可恢复",
                details={"audit_run_id": context.audit_run_id},
            )

    def _require_authorized(
        self, role: ActorRole, action: DecisionAction, scope: DecisionScope
    ) -> None:
        if action not in self._authz.allowed_actions(role, scope):
            raise ActionNotAuthorizedError(
                "当前角色无权执行该动作",
                details={"role": role.value, "action": action.value, "scope": scope.value},
            )

    def _require_action_payload(
        self,
        *,
        action: DecisionAction,
        scope: DecisionScope,
        reason: str | None,
        payload: dict[str, Any],
        risk_item_id: str | None,
        previous_decision_id: str | None,
    ) -> None:
        if action in _CASE_ONLY_ACTIONS and scope is not DecisionScope.CASE:
            raise ActionNotAllowedError(f"{action.value} 仅允许案件级决定")
        if action in _RISK_ITEM_ONLY_ACTIONS and scope is not DecisionScope.RISK_ITEM:
            raise ActionNotAllowedError(f"{action.value} 仅允许风险项级决定")
        if scope is DecisionScope.RISK_ITEM and not risk_item_id:
            raise InvalidActionPayloadError("风险项级决定必须携带 risk_item_id")
        if action in _REASON_REQUIRED_ACTIONS and not (reason and reason.strip()):
            raise InvalidActionPayloadError(f"{action.value} 必须提供人工理由 reason")
        if action is DecisionAction.EDIT:
            if "before_value" not in payload or "after_value" not in payload:
                raise InvalidActionPayloadError(
                    "edit 必须携带 before_value 与 after_value（不得覆盖原始记录）"
                )
        if action is DecisionAction.REQUEST_SUPPLEMENT:
            if not payload.get("requested_supplements"):
                raise InvalidActionPayloadError(
                    "request_supplement 必须列出 requested_supplements"
                )
        if action in (DecisionAction.TRANSFER, DecisionAction.ESCALATE):
            if not (payload.get("target_queue_code") or payload.get("target_actor_id")):
                raise InvalidActionPayloadError(
                    f"{action.value} 必须提供目标队列或目标责任人"
                )
            if not payload.get("handoff_question"):
                raise InvalidActionPayloadError(f"{action.value} 必须提供 handoff_question")
        if action is DecisionAction.ACCEPT_RISK and not payload.get("authorization_ref"):
            raise InvalidActionPayloadError("accept_risk 必须携带 authorization_ref")
        if action in (DecisionAction.WITHDRAW, DecisionAction.CORRECT) and not previous_decision_id:
            raise InvalidActionPayloadError(f"{action.value} 必须引用 previous_decision_id")

    def _require_approvable(
        self, context: ContextTriple, evidence_refs: list[dict[str, Any]]
    ) -> None:
        pending = self._validator.pending_required_risk_items(context)
        if pending:
            raise ActionNotAllowedError(
                "存在未处置的必处置风险项，不能批准",
                details={"pending_risk_item_ids": pending},
            )
        if not self._validator.evidence_complete(context):
            raise EvidenceIncompleteError(
                "证据不完整，不能批准", details={"audit_run_id": context.audit_run_id}
            )
        if not evidence_refs:
            raise EvidenceIncompleteError("案件级批准的 evidence_refs 不得为空")

    def _apply_assignment_projection(
        self, assignment: ReviewAssignment, action: DecisionAction, payload: dict[str, Any]
    ) -> ReviewAssignment | None:
        """更新待办投影。转交/升级先建后继待办再替代原待办；失败保持原责任。"""

        now = self._clock()
        if action in (DecisionAction.TRANSFER, DecisionAction.ESCALATE):
            successor = ReviewAssignment(
                assignment_id=_new_id("assignment"),
                context=assignment.context,
                queue_code=payload.get("target_queue_code") or assignment.queue_code,
                routing_reasons=list(assignment.routing_reasons),
                priority=(
                    Priority.URGENT if action is DecisionAction.ESCALATE else assignment.priority
                ),
                assignee_id=payload.get("target_actor_id"),
                interrupt_id=assignment.interrupt_id,
                created_at=now,
            )
            self._store.add_assignment(successor)
            assignment.status = AssignmentStatus.SUPERSEDED
            assignment.closed_at = now
            assignment.revision += 1
            self._audit(
                AuditEventType.ASSIGNMENT_SUPERSEDED,
                assignment.context,
                actor_id=None,
                summary=f"待办已{action.value}至 {successor.queue_code}",
                details={
                    "superseded_assignment_id": assignment.assignment_id,
                    "successor_assignment_id": successor.assignment_id,
                },
            )
            return successor
        if action in (
            DecisionAction.APPROVE,
            DecisionAction.REJECT,
            DecisionAction.REQUEST_SUPPLEMENT,
        ):
            assignment.status = AssignmentStatus.COMPLETED
            assignment.closed_at = now
        else:
            assignment.status = AssignmentStatus.IN_PROGRESS
        return None

    def _resume_interrupt(
        self,
        assignment: ReviewAssignment,
        decision: HumanDecision,
        action: DecisionAction,
        reason: str | None,
        payload: dict[str, Any],
    ) -> HitlInterrupt | None:
        """按当前有效上下文恢复图执行；无可恢复中断时不视为错误。

        恢复前置校验（hitl arch 6.2）已在 submit_decision 中完成；
        此处仅消费仍处于 pending 的中断并委托适配层恢复。
        转交/升级保持人工路径（新待办继续承载同一中断），不触发恢复。
        """
        if action in (DecisionAction.TRANSFER, DecisionAction.ESCALATE):
            return None
        interrupt = (
            self._store.get_interrupt(assignment.interrupt_id)
            if assignment.interrupt_id
            else None
        )
        if interrupt is None or interrupt.status is not InterruptStatus.PENDING:
            return None

        resume_value = {
            "action": action.value,
            "decision_id": decision.decision_id,
            "reason": reason,
            "payload": payload,
        }
        ensure_json_serializable(resume_value, what="恢复值")
        command = ResumeCommand(
            interrupt_id=interrupt.interrupt_id,
            decision_id=decision.decision_id,
            action=action.value,
            value=resume_value,
        )
        self._graph.resume(interrupt.thread_id, command)
        interrupt.status = InterruptStatus.RESUMED
        interrupt.decision_id = decision.decision_id
        interrupt.resolved_at = self._clock()
        self._audit(
            AuditEventType.INTERRUPT_RESUMED,
            interrupt.context,
            actor_id=decision.actor_id,
            summary="HITL 中断已按人工决定恢复",
            details={
                "interrupt_id": interrupt.interrupt_id,
                "thread_id": interrupt.thread_id,
                "decision_id": decision.decision_id,
            },
        )
        return interrupt

    def _outcome_for_replay(
        self, decision: HumanDecision, assignment: ReviewAssignment
    ) -> DecisionOutcome:
        return DecisionOutcome(
            decision=decision,
            case_status_effect=_CASE_STATUS_EFFECT.get(decision.action, "human_reviewing"),
            assignment=assignment,
            successor_assignment=None,
            resumed_interrupt=None,
            audit_event_ids=[],
        )

    def _audit(
        self,
        event_type: AuditEventType,
        context: ContextTriple,
        *,
        actor_id: str | None,
        summary: str,
        details: dict[str, Any],
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=_new_id("evt"),
            event_type=event_type,
            context=context,
            actor_id=actor_id,
            summary=summary,
            details=details,
            occurred_at=self._clock(),
        )
        self._store.append_audit_event(event)
        return event
