# Implementation status

Report date: 2026-11-17 · Version 0.1.0 (first vertical slice). Feature-level checklist:
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Gaps: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## Summary

The vertical slice from spec section 32 works end to end and was verified in a real browser against PostgreSQL +
pgvector with real SMTP delivery to Mailpit, using the **mock** AI provider. No production deployment exists, and
no real AI provider was called.

## Features implemented and tested

| Feature | Evidence |
| --- | --- |
| Registration, email verification (single use, expiry), login, logout, sessions, reset, change password, lockout, CSRF, Origin, rate limit, enumeration protection | `tests/api/test_auth.py` (13 tests) + e2e |
| Role enforcement, IDOR, cross-company isolation, mass assignment, self-verification, suspension, XSS/SQLi payloads, pagination caps, upload type checks, prompt injection in resumes | `tests/security/test_authorization.py` (18 tests) |
| Resume upload (PDF/DOCX), processing, retry, consent-gated AI vs. heuristics, fact review without silent overwrite | `tests/api/test_vertical_slice.py`, unit tests, e2e |
| Company verification, job lifecycle, optimistic locking, unverified company cannot publish, advisory job parsing | `test_vertical_slice.py`, e2e |
| Recommendations, explanations, eligibility semantics, ranking monotonicity | unit + API tests + e2e |
| Cover-letter generation, versioning, unsupported-claim detection | unit + API tests + e2e |
| Idempotent candidate-approved submission, duplicate prevention, external-job handling | `test_vertical_slice.py`, e2e |
| Employer review, viewed timestamp, audited resume download, state machine, candidate notification | `test_vertical_slice.py`, e2e |
| Export and account deletion | `test_vertical_slice.py`, e2e |
| AI client: malformed output recovery, bounded retries, no retry on refusal, circuit breaker, production rejects mock | `tests/unit/test_ai_client.py` |
| Documents: magic bytes, macros, PDF JavaScript, oversize, filename sanitization, scanned PDF without OCR | `tests/unit/test_core_units.py` |
| UI components: accessible Field, MatchScore text label, client schemas | `apps/web/src/components/ui.test.tsx` |

Implemented but **not** covered by automated tests: interview scheduling via the UI, admin reports/tasks/taxonomy
endpoints, notification preferences, saved jobs, Celery worker mode (`TASK_MODE=celery`), S3/MinIO storage,
ClamAV, Tesseract OCR, the Anthropic adapter, the OpenAI-compatible embedder.

## Commands executed and results

| Command | Result |
| --- | --- |
| `uv sync --python 3.12` (services/api) | OK, lockfile `uv.lock` |
| `pytest` (SQLite, mock AI) | **77 passed** |
| `TEST_DATABASE_URL=postgresql+psycopg://…/careerpilot_test pytest` | **77 passed** (first run surfaced a VARCHAR length bug, now fixed) |
| `alembic upgrade head` → `alembic check` → `alembic downgrade base` → `alembic upgrade head` | OK, "No new upgrade operations detected" |
| `python -m careerpilot.cli seed-skills` | 134 skills added |
| `ruff check .` / `ruff format --check .` | All checks passed / 73 files formatted |
| `mypy careerpilot` | No issues in 60 source files |
| `npm install` (apps/web) | 0 vulnerabilities reported |
| `npx tsc --noEmit` | OK |
| `npx eslint .` | OK (0 problems) |
| `npx vitest run` | **7 passed** |
| `npx next build` | OK, 25 routes |
| `npx playwright test` (live stack: uvicorn + `next start` + PostgreSQL + Mailpit) | **1 passed** (full journey, ~31 s) |
| `docker compose config -q` | OK |
| `docker compose up -d postgres redis mailpit` | Containers healthy |

Not executed: `docker compose up --build` for the full stack (api/worker/web/minio images were not built in this
session), the GitHub Actions workflow (no remote repository), `pip-audit` and gitleaks (configured in CI only),
real-provider AI calls, load or performance benchmarks, a restore drill, axe/screen-reader accessibility audits.

## Security checks performed

Automated security test suite (above); CSRF/Origin/enumeration/lockout tests; tokens and sessions stored only as
hashes (asserted); upload hardening tests; configuration safety validation test; `npm install` audit summary. No
SAST tool or external penetration test was run.

## Required environment variables

Minimum for local development: `DATABASE_URL`. Production: see [DEPLOYMENT.md](DEPLOYMENT.md#required-configuration-production)
and [.env.example](../.env.example).

## External integrations still requiring configuration

| Integration | Variables | State |
| --- | --- | --- |
| Anthropic Claude | `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, `LLM_MODEL` | Implemented, not live-tested |
| Embedding API | `EMBEDDING_PROVIDER=openai_compatible`, `EMBEDDING_API_BASE`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `EMBEDDING_API_KEY` | Implemented, not live-tested |
| SMTP | `EMAIL_PROVIDER=smtp`, `SMTP_*` | Verified with Mailpit |
| S3 / MinIO | `STORAGE_PROVIDER=s3`, `S3_*` | Implemented, not exercised |
| ClamAV | `MALWARE_SCANNER=clamav`, `CLAMAV_*` | Implemented, not exercised |
| Tesseract OCR | `OCR_PROVIDER=tesseract` + `uv sync --extra ocr` + binary | Implemented, not exercised |
| Redis + Celery | `REDIS_URL`, `TASK_MODE=celery` | Implemented, worker not run in this session |

## Outstanding tasks

Resume tailoring; team invitations and roles; MFA and OAuth; email change; interview prep and career guidance;
skill-gap view; saved-jobs page; moderation queue for `pending_review`; retention purge jobs and Celery beat;
evaluation harness and labeled datasets; ANN index; nonce-based CSP; billing extension points; full Compose run;
CI run on GitHub; restore drill; accessibility audit; rendered diagram images.

## Recommended next steps

1. Push to a Git remote and let CI run (lint, types, tests on both databases, audits, image builds).
2. Run `docker compose up --build` and the Playwright journey against it; fix any container issues.
3. Configure an Anthropic key in a dev environment, run the smoke test from TESTING.md, then build a small
   labeled extraction set and compare LLM and heuristic extraction.
4. Implement admin MFA before any non-local deployment.
5. Build the evaluation harness, then replace the hashing embedder and calibrate ranking weights.
6. Next product increment: resume tailoring (with the same claim checks), team invitations, saved-jobs UI.
