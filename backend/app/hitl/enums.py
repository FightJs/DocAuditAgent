"""HITL 领域枚举。

取值遵循 `docs/08_api_spec/api_spec-v1.0.md` 3.1 约定：枚举值使用小写 snake_case；
未知枚举由 API 层降级处理，本模块不接受规范外的取值。
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """Python 3.10 兼容的字符串枚举（值即 API 契约中的 snake_case 字面量）。"""

    def __str__(self) -> str:  # pragma: no cover - 便于日志/序列化
        return self.value


class InterruptPoint(StrEnum):
    """HITL 中断点，对应 langchain_hitl_document_audit_arch-v1.0.md 第 5 节。"""

    PARSE_INTAKE_EXCEPTION = "parse_intake_exception"  # 解析/准入异常确认
    RISK_TRIAGE = "risk_triage"  # 风险分流确认
    RISK_ITEM_REVIEW = "risk_item_review"  # 风险项人工复核
    CASE_FINAL_DECISION = "case_final_decision"  # 案件级最终决定


class InterruptStatus(StrEnum):
    PENDING = "pending"  # 暂停等待人工输入
    RESUMED = "resumed"  # 已被有效人工决定恢复
    INVALIDATED = "invalidated"  # 上下文失效，不可恢复（旧流程只读）


class RoutingReason(StrEnum):
    """进入人工路径的触发原因，对应 human_interaction_decision_models.md 1.1。"""

    REDLINE = "redline"
    HIGH_SEVERITY = "high_severity"
    LOW_CONFIDENCE = "low_confidence"
    EVIDENCE_GAP = "evidence_gap"
    PARSE_QUALITY = "parse_quality"
    RULE_CONFLICT = "rule_conflict"
    SUBMITTER_OBJECTION = "submitter_objection"
    MANUAL_ROUTE = "manual_route"


class Priority(StrEnum):
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class AssignmentStatus(StrEnum):
    """人工待办生命周期（对应 ReviewSession 3.3 的 MVP 语义）。"""

    QUEUED = "queued"  # 待认领
    ACCEPTED = "accepted"  # 已认领
    IN_PROGRESS = "in_progress"  # 处理中
    COMPLETED = "completed"  # 已随有效决定结束
    SUPERSEDED = "superseded"  # 被转交/升级/新版本替代
    EXPIRED = "expired"  # 租约到期未处理


class DecisionScope(StrEnum):
    CASE = "case"  # 案件级（对应数据模型 TASK）
    RISK_ITEM = "risk_item"  # 风险项级（对应数据模型 FINDING）


class DecisionAction(StrEnum):
    """人工动作，对应 api_spec-v1.0.md 6.3 统一决定入口。"""

    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    REQUEST_SUPPLEMENT = "request_supplement"
    TRANSFER = "transfer"
    ESCALATE = "escalate"
    ACCEPT_RISK = "accept_risk"
    WITHDRAW = "withdraw"
    CORRECT = "correct"


class DecisionResult(StrEnum):
    ACCEPTED = "accepted"
    REJECTED_STALE = "rejected_stale"
    REJECTED_UNAUTHORIZED = "rejected_unauthorized"
    REJECTED_VALIDATION = "rejected_validation"
    SUPERSEDED = "superseded"


class ActorRole(StrEnum):
    """操作者角色快照，对应 api_spec-v1.0.md 3.2 角色语义。"""

    SUBMITTER = "submitter"
    REVIEWER = "reviewer"
    EXPERT = "expert"
    APPROVER = "approver"
    POLICY_OWNER = "policy_owner"
    OPERATOR = "operator"
    ADMIN = "admin"


class AuditEventType(StrEnum):
    INTERRUPT_OPENED = "interrupt_opened"
    ASSIGNMENT_ACCEPTED = "assignment_accepted"
    DECISION_RECORDED = "decision_recorded"
    DECISION_SUPERSEDED = "decision_superseded"
    ASSIGNMENT_SUPERSEDED = "assignment_superseded"
    INTERRUPT_RESUMED = "interrupt_resumed"
    INTERRUPT_INVALIDATED = "interrupt_invalidated"
