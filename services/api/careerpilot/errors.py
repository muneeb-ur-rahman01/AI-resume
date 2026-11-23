"""Consistent, safe API errors.

Every error response has the shape::

    {"error": {"code": "machine_readable_code", "message": "Safe message", "details": {...}, "request_id": "..."}}

Internal exceptions are logged with the request id and returned as a generic 500.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("careerpilot.errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthenticated"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"


def _body(request: Request, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = {"Retry-After": str(exc.details.get("retry_after", 60))} if isinstance(exc, RateLimited) else None
        return JSONResponse(
            _body(request, exc.code, exc.message, exc.details), status_code=exc.status_code, headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Only expose field locations and messages, never the submitted values (may contain secrets).
        fields = [
            {"loc": [str(p) for p in err.get("loc", [])], "msg": str(err.get("msg", "invalid"))} for err in exc.errors()
        ]
        return JSONResponse(
            _body(request, "validation_failed", "The request is invalid.", {"fields": fields}), status_code=422
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}.get(
            exc.status_code, "http_error"
        )
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(_body(request, code, message), status_code=exc.status_code)

    @app.exception_handler(OperationalError)
    async def _db_down(request: Request, exc: OperationalError) -> JSONResponse:
        logger.error("database_unavailable", extra={"request_id": getattr(request.state, "request_id", None)})
        return JSONResponse(
            _body(request, "service_unavailable", "The service is temporarily unavailable."), status_code=503
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"request_id": getattr(request.state, "request_id", None)})
        return JSONResponse(_body(request, "internal_error", "An unexpected error occurred."), status_code=500)
