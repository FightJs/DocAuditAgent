"""HTTP routes for the backend MVP.

Authentication is represented by trusted hosting-layer headers for local MVP
testing. All authorization and state decisions remain server-side in
``AuditService``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from app.hitl.enums import ActorRole
from app.schemas import (
    AcceptAssignmentRequest,
    ActorContext,
    CreateCaseRequest,
    CreateDeliveryRequest,
    CreateObjectionRequest,
    CreateUploadBatchRequest,
    SubmitDecisionRequest,
    SubmitUploadBatchRequest,
)
from app.services.audit_service import AuditService
from app.services.errors import InvalidRequestError, UnauthenticatedError


router = APIRouter(prefix="/api/v1")


def get_service(request: Request) -> AuditService:
    return request.app.state.audit_service


def get_actor(
    x_actor_id: Annotated[str | None, Header(alias="X-Actor-ID")] = None,
    x_actor_role: Annotated[str | None, Header(alias="X-Actor-Role")] = None,
) -> ActorContext:
    if not x_actor_id or not x_actor_role:
        raise UnauthenticatedError("缺少已认证主体信息")
    try:
        role = ActorRole(x_actor_role)
    except ValueError as exc:
        raise UnauthenticatedError("主体角色无效") from exc
    return ActorContext(actor_id=x_actor_id, role=role)


Actor = Annotated[ActorContext, Depends(get_actor)]
Service = Annotated[AuditService, Depends(get_service)]


def envelope(data: Any, *, page: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"data": data}
    if page is not None:
        result["page"] = page
    return result


def require_idempotency(key: str | None) -> str:
    if not key:
        raise InvalidRequestError("Idempotency-Key 请求头必填")
    return key


@router.post("/cases", status_code=201)
def create_case(
    payload: CreateCaseRequest,
    response: Response,
    actor: Actor,
    service: Service,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    data, status, replay = service.create_case(
        payload, actor, require_idempotency(idempotency_key)
    )
    response.status_code = status
    response.headers["Idempotent-Replay"] = str(replay).lower()
    return envelope(data)


@router.get("/cases")
def list_cases(
    actor: Actor,
    service: Service,
    status: str | None = None,
) -> dict[str, Any]:
    return envelope(service.list_cases(actor, status=status), page={"next_cursor": None})


@router.get("/cases/{case_id}")
def get_case(case_id: str, actor: Actor, service: Service) -> dict[str, Any]:
    return envelope(service.get_case(case_id, actor))


@router.post("/cases/{case_id}/upload-batches", status_code=201)
def create_upload_batch(
    case_id: str,
    payload: CreateUploadBatchRequest,
    response: Response,
    actor: Actor,
    service: Service,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    data, status, replay = service.create_upload_batch(
        case_id, payload, actor, require_idempotency(idempotency_key)
    )
    response.status_code = status
    response.headers["Idempotent-Replay"] = str(replay).lower()
    return envelope(data)


@router.put("/upload-sessions/{upload_session_id}/content")
async def upload_content(
    upload_session_id: str,
    request: Request,
    actor: Actor,
    service: Service,
) -> dict[str, Any]:
    content = await request.body()
    return envelope(service.upload_content(upload_session_id, content, actor))


@router.post("/upload-batches/{upload_batch_id}/submit", status_code=202)
def submit_upload_batch(
    upload_batch_id: str,
    payload: SubmitUploadBatchRequest,
    response: Response,
    actor: Actor,
    service: Service,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    data, status, replay = service.submit_upload_batch(
        upload_batch_id, payload, actor, require_idempotency(idempotency_key)
    )
    response.status_code = status
    response.headers["Idempotent-Replay"] = str(replay).lower()
    return envelope(data)


@router.get("/cases/{case_id}/timeline")
def get_timeline(
    case_id: str,
    actor: Actor,
    service: Service,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    data, page = service.get_timeline(case_id, actor, cursor=cursor, limit=limit)
    return envelope(data, page=page)


@router.get("/cases/{case_id}/document-versions/{document_version_id}")
def get_document_version(
    case_id: str, document_version_id: str, actor: Actor, service: Service
) -> dict[str, Any]:
    return envelope(service.get_document_version(case_id, document_version_id, actor))


@router.get(
    "/cases/{case_id}/document-versions/{document_version_id}/material-requests"
)
def list_material_requests(
    case_id: str, document_version_id: str, actor: Actor, service: Service
) -> dict[str, Any]:
    return envelope(service.list_material_requests(case_id, document_version_id, actor))


@router.get("/cases/{case_id}/audit-runs/{audit_run_id}")
def get_audit_run(
    case_id: str, audit_run_id: str, actor: Actor, service: Service
) -> dict[str, Any]:
    return envelope(service.get_audit_run(case_id, audit_run_id, actor))


@router.get("/cases/{case_id}/audit-runs/{audit_run_id}/result")
def get_audit_result(
    case_id: str, audit_run_id: str, actor: Actor, service: Service
) -> dict[str, Any]:
    return envelope(service.get_audit_result(case_id, audit_run_id, actor))


@router.get("/cases/{case_id}/findings")
def list_current_findings(
    case_id: str, actor: Actor, service: Service
) -> dict[str, Any]:
    return envelope(service.list_current_case_findings(case_id, actor))


@router.get("/cases/{case_id}/audit-runs/{audit_run_id}/findings")
def list_findings(
    case_id: str,
    audit_run_id: str,
    actor: Actor,
    service: Service,
    status: str | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    return envelope(
        service.list_findings(
            case_id, audit_run_id, actor, status=status, severity=severity
        ),
        page={"next_cursor": None},
    )


@router.get("/cases/{case_id}/audit-runs/{audit_run_id}/findings/{finding_id}")
def get_finding(
    case_id: str,
    audit_run_id: str,
    finding_id: str,
    actor: Actor,
    service: Service,
) -> dict[str, Any]:
    return envelope(service.get_finding(case_id, audit_run_id, finding_id, actor))


@router.get("/cases/{case_id}/audit-runs/{audit_run_id}/locators/{locator_id}")
def get_locator(
    case_id: str,
    audit_run_id: str,
    locator_id: str,
    actor: Actor,
    service: Service,
) -> dict[str, Any]:
    return envelope(service.get_locator(case_id, audit_run_id, locator_id, actor))


@router.get("/review-queues/{queue_id}/assignments")
def list_assignments(
    queue_id: str,
    actor: Actor,
    service: Service,
    status: str | None = None,
) -> dict[str, Any]:
    return envelope(
        service.list_assignments(queue_id, actor, status=status),
        page={"next_cursor": None},
    )


@router.get("/cases/{case_id}/assignments/{assignment_id}")
def get_assignment(
    case_id: str, assignment_id: str, actor: Actor, service: Service
) -> dict[str, Any]:
    return envelope(service.get_assignment(case_id, assignment_id, actor))


@router.post("/cases/{case_id}/assignments/{assignment_id}/accept")
def accept_assignment(
    case_id: str,
    assignment_id: str,
    payload: AcceptAssignmentRequest,
    actor: Actor,
    service: Service,
) -> dict[str, Any]:
    return envelope(
        service.accept_assignment(
            case_id,
            assignment_id,
            expected_revision=payload.expected_revision,
            idempotency_key=payload.idempotency_key,
            actor=actor,
        )
    )


@router.post("/cases/{case_id}/assignments/{assignment_id}/decisions", status_code=201)
def submit_decision(
    case_id: str,
    assignment_id: str,
    payload: SubmitDecisionRequest,
    actor: Actor,
    service: Service,
) -> dict[str, Any]:
    return envelope(service.submit_decision(case_id, assignment_id, payload, actor))


@router.post("/cases/{case_id}/objections", status_code=201)
def create_objection(
    case_id: str,
    payload: CreateObjectionRequest,
    actor: Actor,
    service: Service,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    return envelope(
        service.create_objection(
            case_id, payload, actor, require_idempotency(idempotency_key)
        )
    )


@router.post("/cases/{case_id}/deliveries", status_code=201)
def create_delivery(
    case_id: str,
    payload: CreateDeliveryRequest,
    actor: Actor,
    service: Service,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    return envelope(
        service.create_delivery(
            case_id, payload, actor, require_idempotency(idempotency_key)
        )
    )


@router.get("/cases/{case_id}/deliveries/{delivery_id}")
def get_delivery(
    case_id: str, delivery_id: str, actor: Actor, service: Service
) -> dict[str, Any]:
    return envelope(service.get_delivery(case_id, delivery_id, actor))

