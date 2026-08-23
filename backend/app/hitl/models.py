"""HITL 领域模型（纯 stdlib dataclass，append-only 事实 + 可变投影分离）。

依据：
- `docs/07_data_model/human_interaction_decision_models.md`（决定追加不可变、版本绑定、乐观锁）
- `docs/06_system_architecture/langchain_hitl_document_audit_arch-v1.0.md`（thread_id/checkpoint 边界）
- `docs/08_api_spec/api_spec-v1.0.md`（版本/运行/基线三元组上下文）

注意：本模块的内存模型是 MVP 运行时表示；持久化表结构由数据模型阶段与
后续存储实现承接，checkpoint 不替代业务决定与审计事件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

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


@dataclass(frozen=True)
class ContextTriple:
    """人工动作/HITL 恢复的唯一有效上下文：版本 + 运行 + 基线。"""

    case_id: str
    document_version_id: str
    audit_run_id: str
    baseline_version_id: str


@dataclass
class ReviewAssignment:
    """人工待办（ReviewSession 的 MVP 投影）。

    同一 `audit_run_id` 任一时刻最多存在一条活跃（queued/accepted/in_progress）待办，
    由 store/service 层保证。转交/升级通过创建后继待办 + 原待办置 superseded 表达。
    """

    assignment_id: str
    context: ContextTriple
    queue_code: str
    routing_reasons: list[RoutingReason]
    priority: Priority = Priority.NORMAL
    status: AssignmentStatus = AssignmentStatus.QUEUED
    assignee_id: str | None = None
    assignee_role: ActorRole | None = None
    revision: int = 1
    interrupt_id: str | None = None
    dedup_key: str | None = None  # 中断节点重执行时的待办去重键
    created_at: datetime | None = None
    expires_at: datetime | None = None
    closed_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status in (
            AssignmentStatus.QUEUED,
            AssignmentStatus.ACCEPTED,
            AssignmentStatus.IN_PROGRESS,
        )


@dataclass
class HitlInterrupt:
    """HITL 中断记录：关联内部 thread_id，业务恢复边界由 context 决定。

    `payload` 为发送给人工界面的最小必要、JSON 可序列化摘要；
    原文与完整证据由受控查询按权限提供，不进入中断 payload。
    """

    interrupt_id: str
    thread_id: str
    point: InterruptPoint
    context: ContextTriple
    payload: dict[str, Any]
    status: InterruptStatus = InterruptStatus.PENDING
    decision_id: str | None = None
    created_at: datetime | None = None
    resolved_at: datetime | None = None


@dataclass
class HumanDecision:
    """人工决定（append-only 事实）。

    拒绝类结果（rejected_*）也作为事实保留，但只有 ACCEPTED 产生状态效果。
    历史决定只读；撤回/更正通过新增决定并将旧决定 is_current 置 False 表达。
    """

    decision_id: str
    assignment_id: str
    context: ContextTriple
    scope: DecisionScope
    action: DecisionAction
    actor_id: str
    actor_role: ActorRole
    reason: str | None
    evidence_refs: list[dict[str, Any]]
    payload: dict[str, Any]
    idempotency_key: str
    request_fingerprint: str  # 幂等重放校验：同键不同请求摘要即冲突
    risk_item_id: str | None = None
    previous_decision_id: str | None = None
    supersedes_decision_id: str | None = None
    bulk_batch_id: str | None = None
    interrupt_id: str | None = None
    result: DecisionResult = DecisionResult.ACCEPTED
    is_current: bool = True
    submitted_at: datetime | None = None
    recorded_at: datetime | None = None


@dataclass
class AuditEvent:
    """追加式审计事件：可还原主体、时间、对象、状态迁移与上下文。"""

    event_id: str
    event_type: AuditEventType
    context: ContextTriple
    actor_id: str | None
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime | None = None


@dataclass(frozen=True)
class DecisionOutcome:
    """决定受理结果：建议的案件状态效果由 services 层（Teammate 3）裁决落库。

    HITL 模块不拥有案件聚合；`case_status_effect` 仅供上层编排参考，
    `approved` 语义仍以后端权威案件状态为准。
    """

    decision: HumanDecision
    case_status_effect: str
    assignment: ReviewAssignment
    successor_assignment: ReviewAssignment | None
    resumed_interrupt: HitlInterrupt | None
    audit_event_ids: list[str]
