"""Service-layer errors mapped by the API layer to the v1 error envelope."""

from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    """Business/API error with a stable contract code."""

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


class InvalidRequestError(ServiceError):
    code = "invalid_request"
    http_status = 400


class UnauthenticatedError(ServiceError):
    code = "unauthenticated"
    http_status = 401


class ActionNotAuthorizedServiceError(ServiceError):
    code = "action_not_authorized"
    http_status = 403


class VisibilityDeniedError(ServiceError):
    code = "visibility_denied"
    http_status = 403


class ResourceNotFoundError(ServiceError):
    code = "resource_not_found"
    http_status = 404


class CaseNotFoundError(ServiceError):
    code = "case_not_found"
    http_status = 404


class RevisionConflictServiceError(ServiceError):
    code = "revision_conflict"
    http_status = 409


class IdempotencyConflictServiceError(ServiceError):
    code = "idempotency_conflict"
    http_status = 409


class CaseReferenceConflictError(ServiceError):
    code = "case_reference_conflict"
    http_status = 409


class UploadSessionConflictError(ServiceError):
    code = "upload_session_conflict"
    http_status = 409


class UploadSessionExpiredError(ServiceError):
    code = "upload_session_expired"
    http_status = 409


class UploadIncompleteError(ServiceError):
    code = "upload_incomplete"
    http_status = 422


class ActionNotAllowedServiceError(ServiceError):
    code = "action_not_allowed"
    http_status = 422


class MaterialsRequestedError(ServiceError):
    code = "materials_requested"
    http_status = 422
