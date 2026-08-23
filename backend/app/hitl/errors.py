"""HITL 领域错误。

错误码与 HTTP 语义对齐 `docs/08_api_spec/api_spec-v1.0.md` 第 8 节，
由 API 层（Teammate 3）映射为统一错误 envelope；本模块不感知 HTTP。
"""

from __future__ import annotations

from typing import Any


class HitlError(Exception):
    """HITL 领域错误基类。`code` 即 API 契约中的 error.code。"""

    code = "internal_error"
    http_status = 500
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if retryable is not None:
            self.retryable = retryable

    def to_error_body(self) -> dict[str, Any]:
        """供 API 层组装统一错误 envelope（request_id 由 API 层补充）。"""

        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }


class InvalidActionPayloadError(HitlError):
    code = "invalid_action_payload"
    http_status = 400


class ActionNotAuthorizedError(HitlError):
    code = "action_not_authorized"
    http_status = 403


class AssignmentNotFoundError(HitlError):
    code = "assignment_not_found"
    http_status = 404


class RevisionConflictError(HitlError):
    code = "revision_conflict"
    http_status = 409


class IdempotencyConflictError(HitlError):
    code = "idempotency_conflict"
    http_status = 409


class RunSupersededError(HitlError):
    """暂停流程绑定的版本/基线/运行已被替代，旧 thread 不可恢复。"""

    code = "run_superseded"
    http_status = 409


class StaleHumanTaskError(HitlError):
    """人工待办/中断上下文已过期（被替代、失效或已完成）。"""

    code = "stale_human_task"
    http_status = 409


class AssignmentAlreadyTakenError(HitlError):
    code = "assignment_already_taken"
    http_status = 409


class ActionNotAllowedError(HitlError):
    code = "action_not_allowed"
    http_status = 422


class EvidenceIncompleteError(HitlError):
    code = "evidence_incomplete"
    http_status = 422
