"""Liveness/readiness probes. Responses never include connection strings or versions of dependencies."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from careerpilot.config import get_settings
from careerpilot.db import get_engine

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
    url = get_settings().redis_url
    if url:
        try:
            import redis

            redis.Redis.from_url(url, socket_timeout=1).ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
    ok = all(v == "ok" for v in checks.values())
    s = get_settings()
    body = {
        "status": "ok" if ok else "degraded",
        "checks": checks,
        "ai": {
            "llm_provider": s.llm_provider,
            "mock": s.llm_provider == "mock",
            "embedding_provider": s.embedding_provider,
        },
    }
    return JSONResponse(body, status_code=200 if ok else 503)
