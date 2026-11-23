"""FastAPI application factory."""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from careerpilot import __version__
from careerpilot.config import get_settings
from careerpilot.errors import install_error_handlers
from careerpilot.logging_config import configure_logging, request_id_var

_RID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    import careerpilot.services.resumes  # noqa: F401  (registers background tasks)

    docs_enabled = not settings.is_production_like
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        openapi_url="/api/v1/openapi.json" if docs_enabled else None,
        docs_url="/api/docs" if docs_enabled else None,
        redoc_url=None,
        debug=settings.debug and not settings.is_production_like,
    )
    install_error_handlers(app)

    max_body = settings.max_request_body_mb * 1024 * 1024

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if _RID.match(incoming) else str(uuid.uuid4())
        request.state.request_id = rid
        token = request_id_var.set(rid)
        try:
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > max_body:
                return JSONResponse(
                    {
                        "error": {
                            "code": "payload_too_large",
                            "message": "Request body is too large.",
                            "details": {},
                            "request_id": rid,
                        }
                    },
                    status_code=413,
                )
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if not request.url.path.startswith("/api/docs"):
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if request.url.path.startswith("/api/v1/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Request-ID"],
    )

    from careerpilot.api.routes import admin, auth, candidate, employer, health, public

    for r in (auth.router, candidate.router, employer.router, admin.router, public.router, health.router):
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
