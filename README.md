# CareerPilot AI

An AI career agent: it understands a candidate's resume, finds relevant jobs, explains why they match, helps
prepare truthful applications, and submits them **only after the candidate approves**. Employers publish jobs
(after verification) and review applicants with advisory, explainable relevance signals. Administrators moderate
the platform.

> **Status: first vertical slice (v0.1.0).** The end-to-end loop works: register → verify → upload resume →
> confirm extracted facts → recommendations with explanations → cover letter → approved submission → employer
> review → status tracking → export/delete. Many modules from the full specification are still planned; see
> [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) and
> [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md). Nothing has been deployed to production.

## Contents

1. [Product goals](#product-goals) · 2. [Features](#features) · 3. [Screenshots](#screenshots) ·
4. [Technology stack](#technology-stack) · 5. [System requirements](#system-requirements) ·
6. [Architecture](#architecture) · 7. [Repository structure](#repository-structure) ·
8. [Local development](#local-development) · 9. [Configuration](#environment-configuration) ·
10. [Database and migrations](#database-and-migrations) · 11. [AI providers](#ai-provider-setup) ·
12. [Embeddings and vector search](#embeddings-and-vector-search) · 13. [Object storage](#object-storage) ·
14. [Email](#email) · 15. [Docker](#docker) · 16. [Tests, lint, types](#tests-lint-and-type-checks) ·
17. [API docs](#api-documentation) · 18. [Production build and deployment](#production-build-and-deployment) ·
19. [Security](#security-notes) · 20. [Privacy](#privacy-and-data-handling) ·
21. [Troubleshooting](#troubleshooting) · 22. [Limitations and roadmap](#known-limitations-and-roadmap) ·
23. [Contributing](#contributing) · 24. [License](#license)

## Product goals

- Help candidates find relevant roles and understand **why** they fit, without fabricating qualifications.
- Keep the candidate in control: AI output is a suggestion until confirmed; nothing is submitted without approval.
- Give employers a fair, explainable, advisory view of applicants; never auto-reject on opaque model judgments.
- Be secure and privacy-respecting by default: consent-gated AI, minimal data sharing, export and deletion.

## Features

| Area | Implemented in this slice |
| --- | --- |
| Identity | Email/password registration, single-use expiring email verification, login/logout, password reset, password change, session list and revocation, Argon2id, CSRF, rate limits, lockout, enumeration protection |
| Candidate | Profile, skills, experience, education, preferences; resume upload (PDF/DOCX) with async processing; fact review with provenance; recommendations with explanations; job search; cover-letter drafting with unsupported-claim flags; application preview, approval and idempotent submission; tracking, withdrawal; notifications; consent, export, account deletion |
| Employer | Company profile; verification request (domain signals + admin review); job create/edit/publish/pause/close/archive with optimistic locking; AI-suggested requirements (advisory); applicant inbox and detail; resume download (audited); status changes; interview scheduling; basic analytics |
| Admin | Verification queue, user suspension/reinstatement, abuse reports with job pause/close, company suspension, failed-task retry, audit log search, AI usage and cost metrics, taxonomy management |
| AI | Provider-independent LLM and embedding interfaces; Anthropic adapter (structured outputs); deterministic mock; versioned schemas and prompts; grounding; heuristic fallback; hybrid retrieval (SQL + pgvector); explainable rules-based ranking |

## Screenshots

Real screenshots captured automatically by the Playwright journey (`SCREENSHOT_DIR=../../design/screens npm run e2e`)
against the running stack, with synthetic data and the **mock** AI provider (labeled as such in the UI). All 14
are in [`design/screens/`](design/screens/).

| Match explanation | Application preview |
| --- | --- |
| ![Job detail with match explanation](design/screens/08-job-detail-match-explanation.png) | ![Application preview](design/screens/09-application-preview.png) |
| **Resume fact review** | **Employer applicant detail** |
| ![Resume fact review](design/screens/06-candidate-resume-review.png) | ![Employer applicant detail](design/screens/10-employer-applicant-detail.png) |

## Technology stack

- **Web:** Next.js 16 (App Router), React 19, TypeScript 6 (strict), Tailwind CSS 4, TanStack Query, React Hook
  Form + Zod, Lucide, Vitest + Testing Library, Playwright.
- **API/worker:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, Celery, structured JSON logging.
- **Data:** PostgreSQL 17 + pgvector, Redis 7, S3-compatible storage (MinIO locally).
- **AI:** Anthropic Claude via the official SDK (default `claude-opus-5-5`, configurable), pluggable embeddings,
  pdfplumber, python-docx, optional Tesseract OCR.
- **Ops:** Docker, Docker Compose, GitHub Actions, uv (Python lockfile), npm lockfile.

## System requirements

- Docker 24+ with Compose v2 (for the full stack), **or** for local processes: Python 3.12 + [uv](https://docs.astral.sh/uv/),
  Node.js 22 + npm, and Docker for PostgreSQL/Redis/Mailpit.
- About 4 GB RAM for the full Compose stack.

## Architecture

Modular monolith (FastAPI) + separate Celery worker + Next.js frontend that proxies `/api/v1` so auth cookies stay
first-party. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/AI_ARCHITECTURE.md](docs/AI_ARCHITECTURE.md),
[ADRs](docs/adr/).

```mermaid
flowchart LR
  B[Browser] --> W[web: Next.js]
  W -->|/api/v1| A[api: FastAPI]
  A --> P[(PostgreSQL + pgvector)]
  A --> R[(Redis)]
  R --> K[worker: Celery]
  K --> P
  A --> S[(S3 / MinIO)]
  K --> S
  A --> M[(SMTP)]
  K --> L[(LLM provider)]
  A --> L
```

## Repository structure

```
apps/web/                 Next.js app (src/app routes, src/components, src/lib, e2e/ Playwright)
services/api/             FastAPI API + Celery worker (one package)
  careerpilot/api/        routers, DTO schemas, serializers, auth dependencies
  careerpilot/services/   domain services (auth, profiles, resumes, jobs, matching, generation, applications, privacy, ...)
  careerpilot/ai/         providers, schemas, prompts, taxonomy, heuristics, guarded client
  careerpilot/models/     SQLAlchemy models
  careerpilot/infra/      storage, email, background tasks
  careerpilot/security/   passwords, tokens, rate limiting, URL guards
  alembic/                migrations
  tests/                  unit, api, security tests
docs/                     architecture, security, data model, API guide, ops docs, ADRs, diagrams, openapi.json
design/                   tokens, design system, component inventory, a11y, flows, wireframes, assets, screens
.github/workflows/ci.yml  CI
docker-compose.yml        local stack
```

This deviates from the suggested layout (`ai/`, `database/`, `services/worker/` at the top level) to keep one
importable Python package; see [ADR 0001](docs/adr/0001-modular-monolith.md).

## Local development

### Option A: local processes (fastest feedback)

```bash
# 1. Infrastructure
docker compose up -d postgres redis mailpit

# 2. API
cd services/api
uv sync                                  # or: python -m uv sync
cp ../../.env.example .env               # then edit; defaults work for local dev
uv run alembic upgrade head
uv run python -m careerpilot.cli seed-skills
uv run python -m careerpilot.cli create-admin admin@example.com "Platform Admin"   # prompts for a password
uv run uvicorn careerpilot.main:app --reload --host 127.0.0.1 --port 8000

# 3. Web (new terminal)
cd apps/web
npm ci
API_INTERNAL_URL=http://127.0.0.1:8000 npm run dev    # http://localhost:3000
```

**Windows / PowerShell:** if `uv` is "not recognized", it was installed with pip but its Scripts folder is not on
PATH. Use `python -m uv ...` instead of `uv ...` (for example `python -m uv run alembic upgrade head`). Set
environment variables with `$env:API_INTERNAL_URL="http://127.0.0.1:8000"; npm run dev` rather than the
`VAR=value command` form.

With `EMAIL_PROVIDER=console`, verification links are printed in the API log (`dev_email_body`). With
`EMAIL_PROVIDER=smtp SMTP_HOST=127.0.0.1 SMTP_PORT=1025`, open Mailpit at http://localhost:8025.

### Option B: full Docker Compose stack

```bash
docker compose up --build
docker compose exec api python -m careerpilot.cli create-admin admin@example.com "Platform Admin"
```

Web: http://localhost:3000 · API docs: http://localhost:8000/api/docs · Mailpit: http://localhost:8025 ·
MinIO console: http://localhost:9001. (The Compose file is validated, but the full containerized stack has not
yet been run end-to-end; see the status report.)

## Environment configuration

All settings are environment variables, validated at startup (`services/api/careerpilot/config.py`).
[.env.example](.env.example) documents each one with safe placeholders. Staging/production refuse insecure
combinations (default secret, debug, insecure cookies, mock AI, console email, local storage).

## Database and migrations

```bash
cd services/api
uv run alembic upgrade head                       # apply
uv run alembic revision --autogenerate -m "..."   # new migration (review it!)
uv run alembic check                              # models vs. migrations drift check
uv run alembic downgrade -1
```

The initial migration enables the `vector` extension. Schema reference: [docs/DATA_MODEL.md](docs/DATA_MODEL.md).
On Windows, use `127.0.0.1` instead of `localhost` in `DATABASE_URL`, because IPv6 resolution can stall connections.

## AI provider setup

- Default `LLM_PROVIDER=mock` is a **deterministic test double** (heuristics and templates). Its output is
  labeled "mock" in the UI and refused in staging/production.
- Real provider: `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=...`, optionally `LLM_MODEL` (default
  `claude-opus-5-5`), `LLM_EFFORT`, `LLM_FALLBACKS`, timeouts, retries, concurrency, and cost rates for estimates.
- AI processing of a candidate's data requires their `ai_processing` consent; otherwise local heuristics are used.
- The Anthropic adapter has not been exercised against the live API in this repository. Run the smoke test in
  [docs/TESTING.md](docs/TESTING.md) first.

## Embeddings and vector search

- Default `EMBEDDING_PROVIDER=hashing`: a local, deterministic lexical embedder (no network, weak semantics).
- `EMBEDDING_PROVIDER=openai_compatible` with `EMBEDDING_API_BASE`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`,
  `EMBEDDING_API_KEY` for a hosted model. Vectors are stored per model in `embeddings` (pgvector) and refreshed
  when content changes.
- Retrieval unions SQL filters, skill overlap and pgvector cosine distance; see
  [docs/AI_ARCHITECTURE.md](docs/AI_ARCHITECTURE.md).

## Object storage

`STORAGE_PROVIDER=local` (dev/test, files under `LOCAL_STORAGE_PATH`) or `s3` (AWS S3/MinIO via `S3_*`). Objects
use random keys, are private, and are downloaded via ownership-checked endpoints (5-minute presigned URLs on S3).
Binary files are never stored in PostgreSQL.

## Email

`EMAIL_PROVIDER=console` (development: logged, never sent) or `smtp`. `notifications.email_status` records the
actual provider outcome; queued is never reported as delivered.

## Docker

- `services/api/Dockerfile`: multi-stage, uv-locked, non-root; also used by the worker.
- `apps/web/Dockerfile`: Next.js standalone, non-root; `API_INTERNAL_URL` is a build argument.
- `docker-compose.yml`: postgres (pgvector), redis, minio + bucket init, mailpit, migrate (one-off), api, worker,
  web, with health checks and persistent volumes.

## Tests, lint and type checks

```bash
# API
cd services/api
uv run pytest                                   # SQLite + mock AI
TEST_DATABASE_URL=postgresql+psycopg://careerpilot:careerpilot@127.0.0.1:5432/careerpilot_test uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy careerpilot

# Web
cd apps/web
npm run lint && npm run typecheck && npm test && npm run build
npm run e2e        # needs the running stack; see docs/TESTING.md
```

## API documentation

Swagger UI at `/api/docs` (disabled in staging/production), OpenAPI JSON at `/api/v1/openapi.json`, committed
snapshot at [docs/openapi.json](docs/openapi.json), and conventions in [docs/API_GUIDE.md](docs/API_GUIDE.md).

## Production build and deployment

`npm run build` (web) and the Docker images above. Deployment topology, release steps and the hardening
checklist: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Operations: [docs/OPERATIONS_RUNBOOK.md](docs/OPERATIONS_RUNBOOK.md),
[docs/BACKUP_AND_RECOVERY.md](docs/BACKUP_AND_RECOVERY.md), [docs/INCIDENT_RESPONSE.md](docs/INCIDENT_RESPONSE.md).

## Security notes

See [docs/SECURITY.md](docs/SECURITY.md) and [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md). Highlights: hashed
session/CSRF/verification/reset tokens, server-side RBAC and tenant isolation (404 for non-owners), strict DTOs,
upload hardening, SSRF guard, CSP and security headers, redacted logs, audit trail. MFA is not implemented yet.

## Privacy and data handling

See [docs/PRIVACY_AND_RETENTION.md](docs/PRIVACY_AND_RETENTION.md). AI processing is opt-in, only confirmed facts
feed generation, and export and deletion are self-service. **No legal compliance is claimed.** The document is a
checklist for legal review.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| API hangs connecting to the DB on Windows | Use `127.0.0.1` instead of `localhost` in `DATABASE_URL` |
| "Please verify your email address" on login | Open the link from Mailpit / API log, or use "Resend verification email" |
| Publish fails with `company_not_verified` | An admin must approve the company (admin console), or set `REQUIRE_VERIFIED_COMPANY_TO_PUBLISH=false` in development |
| Resume fails: "looks like a scanned document" | Enable OCR (`OCR_PROVIDER=tesseract` + `uv sync --extra ocr` + Tesseract binary) or upload a text PDF/DOCX |
| `ai_unavailable` errors | Check provider key/limits; heuristics and manual flows keep working |
| Web calls fail with 404 on `/api/v1` | Rebuild the web app with the correct `API_INTERNAL_URL` (rewrites are build-time) |
| `typescript-eslint does not support TS 7` | Keep TypeScript on 6.x (pinned) |

## Known limitations and roadmap

[docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) lists everything not yet built. Next increments:
resume tailoring, team invitations, MFA, the evaluation harness with labeled data, retention jobs, interview prep
and career guidance, billing extension points, and a full containerized run plus a restore drill.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

**No license has been selected.** Until one is chosen, all rights are reserved by the authors. No `LICENSE` file is
included on purpose.
