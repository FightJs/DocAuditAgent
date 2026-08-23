"""DocAuditAgent FastAPI application factory."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.hitl.errors import HitlError
from app.services.audit_service import AuditService
from app.services.errors import ServiceError


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
    request_id: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "retryable": retryable,
                "request_id": request_id,
            }
        },
        headers={"X-Request-ID": request_id},
    )


def create_app(*, service: AuditService | None = None) -> FastAPI:
    app = FastAPI(title="DocAuditAgent Backend", version="1.0.0")
    app.state.audit_service = service or AuditService()

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        return _error_response(
            status_code=exc.http_status,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            retryable=exc.retryable,
            request_id=request.state.request_id,
        )

    @app.exception_handler(HitlError)
    async def hitl_error(request: Request, exc: HitlError) -> JSONResponse:
        return _error_response(
            status_code=exc.http_status,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            retryable=exc.retryable,
            request_id=request.state.request_id,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"path": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
            for item in exc.errors()
        ]
        return _error_response(
            status_code=400,
            code="invalid_request",
            message="请求字段校验失败",
            details={"fields": fields},
            request_id=request.state.request_id,
        )

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    return app


app = create_app()

