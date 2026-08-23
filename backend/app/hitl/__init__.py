"""HITL（Human-in-the-loop）领域模块。

职责：中断开启与待办去重、待办认领、人工决定（append-only）、
乐观并发/幂等、上下文失效后的受控恢复拒绝、审计事件。
图执行 SDK（LangGraph）依赖集中在 graph.py 适配层，本包其余部分不感知 SDK。
"""

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
    HitlError,
    IdempotencyConflictError,
    InvalidActionPayloadError,
    RevisionConflictError,
    RunSupersededError,
    StaleHumanTaskError,
)
from .graph import GraphResumeAdapter, ResumeCommand, StubGraphAdapter, ensure_json_serializable
from .models import (
    AuditEvent,
    ContextTriple,
    DecisionOutcome,
    HitlInterrupt,
    HumanDecision,
    ReviewAssignment,
)
from .policies import (
    AuthorizationPolicy,
    ContextValidator,
    MvpAuthorizationPolicy,
    StaticContextValidator,
)
from .service import HitlService
from .store import InMemoryHitlStore

__all__ = [
    "ActorRole",
    "AssignmentStatus",
    "AuditEventType",
    "DecisionAction",
    "DecisionResult",
    "DecisionScope",
    "InterruptPoint",
    "InterruptStatus",
    "Priority",
    "RoutingReason",
    "HitlError",
    "ActionNotAllowedError",
    "ActionNotAuthorizedError",
    "AssignmentAlreadyTakenError",
    "AssignmentNotFoundError",
    "EvidenceIncompleteError",
    "IdempotencyConflictError",
    "InvalidActionPayloadError",
    "RevisionConflictError",
    "RunSupersededError",
    "StaleHumanTaskError",
    "GraphResumeAdapter",
    "ResumeCommand",
    "StubGraphAdapter",
    "ensure_json_serializable",
    "AuditEvent",
    "ContextTriple",
    "DecisionOutcome",
    "HitlInterrupt",
    "HumanDecision",
    "ReviewAssignment",
    "AuthorizationPolicy",
    "ContextValidator",
    "MvpAuthorizationPolicy",
    "StaticContextValidator",
    "HitlService",
    "InMemoryHitlStore",
]
