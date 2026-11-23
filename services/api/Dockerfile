# API and worker image (same codebase; the worker overrides the command).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

FROM base AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY careerpilot ./careerpilot
RUN uv sync --frozen --no-dev

FROM base AS runtime
RUN groupadd --system app && useradd --system --gid app --home /app app
COPY --from=build /app/.venv /app/.venv
COPY careerpilot ./careerpilot
COPY alembic ./alembic
COPY alembic.ini ./
ENV PATH="/app/.venv/bin:$PATH"
USER app
EXPOSE 8000
# Uvicorn handles SIGTERM gracefully (finishes in-flight requests).
CMD ["uvicorn", "careerpilot.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
