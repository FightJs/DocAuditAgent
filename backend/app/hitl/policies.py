"""HITL 外部依赖缝（seam）：上下文有效性与授权策略。

后端是权限与状态的唯一裁决方（api_spec 3.2 / hitl arch 3.2）。本模块把
“版本/运行/基线是否仍当前有效”“风险项处置与证据是否完备”“角色可执行哪些
动作”抽象为协议，由 services 层（Teammate 3）以真实案件/运行聚合实现；
本文件附带 MVP 默认实现与测试 stub。
"""

from __future__ import annotations

from typing import Protocol

from .enums import ActorRole, DecisionAction, DecisionScope
from .models import ContextTriple


class ContextValidator(Protocol):
    """恢复/决定前的业务上下文校验（由上层以权威业务存储实现）。"""

    def is_current(self, context: ContextTriple) -> bool:
        """版本、基线、审核运行是否仍是当前有效处理对象。"""
        ...

    def pending_required_risk_items(self, context: ContextTriple) -> list[str]:
        """尚未处置、阻塞案件级 approve 的风险项 id 列表。"""
        ...

    def evidence_complete(self, context: ContextTriple) -> bool:
        """当前上下文证据是否完整可复核（无缺失定位/过期证据）。"""
        ...


class AuthorizationPolicy(Protocol):
    """角色 → 可执行动作；案件/队列级细粒度授权由上层补充。"""

    def allowed_actions(self, role: ActorRole, scope: DecisionScope) -> set[DecisionAction]:
        ...


class StaticContextValidator:
    """MVP/测试用静态校验器：可显式标记过期上下文与未处置风险项。"""

    def __init__(self) -> None:
        self._stale_runs: set[str] = set()
        self._pending: dict[str, list[str]] = {}  # audit_run_id -> risk_item_ids
        self._evidence_incomplete_runs: set[str] = set()

    def mark_run_superseded(self, audit_run_id: str) -> None:
        self._stale_runs.add(audit_run_id)

    def set_pending_risk_items(self, audit_run_id: str, risk_item_ids: list[str]) -> None:
        self._pending[audit_run_id] = list(risk_item_ids)

    def mark_evidence_incomplete(self, audit_run_id: str) -> None:
        self._evidence_incomplete_runs.add(audit_run_id)

    def is_current(self, context: ContextTriple) -> bool:
        return context.audit_run_id not in self._stale_runs

    def pending_required_risk_items(self, context: ContextTriple) -> list[str]:
        return list(self._pending.get(context.audit_run_id, []))

    def evidence_complete(self, context: ContextTriple) -> bool:
        return context.audit_run_id not in self._evidence_incomplete_runs


# MVP 默认授权矩阵：仅表达“角色 × 动作粒度”，案件/队列级授权仍由服务端
# 在 API/service 层叠加校验；operator/admin 不获得专业审批权（api_spec 3.2）。
_CASE_ACTIONS_REVIEWER = {
    DecisionAction.EDIT,
    DecisionAction.REQUEST_SUPPLEMENT,
    DecisionAction.TRANSFER,
    DecisionAction.ESCALATE,
    DecisionAction.WITHDRAW,
    DecisionAction.CORRECT,
}
_RISK_ITEM_ACTIONS_REVIEWER = {
    DecisionAction.EDIT,
    DecisionAction.ACCEPT_RISK,
    DecisionAction.REQUEST_SUPPLEMENT,
    DecisionAction.TRANSFER,
    DecisionAction.ESCALATE,
    DecisionAction.WITHDRAW,
    DecisionAction.CORRECT,
}
_CASE_ACTIONS_APPROVER = _CASE_ACTIONS_REVIEWER | {
    DecisionAction.APPROVE,
    DecisionAction.REJECT,
}


class MvpAuthorizationPolicy:
    """MVP 默认授权策略。

    - approve/reject 仅 approver/expert（案件级最终决定需相应授权）。
    - submitter 无任何人工复核动作；operator/admin 仅运营队列，不做审批。
    """

    def allowed_actions(self, role: ActorRole, scope: DecisionScope) -> set[DecisionAction]:
        if role in (ActorRole.APPROVER, ActorRole.EXPERT):
            return set(_CASE_ACTIONS_APPROVER) | set(_RISK_ITEM_ACTIONS_REVIEWER)
        if role is ActorRole.REVIEWER:
            if scope is DecisionScope.CASE:
                return set(_CASE_ACTIONS_REVIEWER)
            return set(_RISK_ITEM_ACTIONS_REVIEWER)
        return set()
