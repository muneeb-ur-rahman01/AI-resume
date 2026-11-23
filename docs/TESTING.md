# Testing

| Suite | Location | Command | External services |
| --- | --- | --- | --- |
| Backend unit + API + security | `services/api/tests/` | `cd services/api && uv run pytest` | None (SQLite in memory, mock AI, console email, local storage, inline tasks) |
| Same suite on PostgreSQL + pgvector | same | `TEST_DATABASE_URL=postgresql+psycopg://careerpilot:careerpilot@127.0.0.1:5432/careerpilot_test uv run pytest` | PostgreSQL (`docker compose up -d postgres`; create the `careerpilot_test` DB once) |
| Migrations | `services/api/alembic` | `uv run alembic upgrade head && uv run alembic check && uv run alembic downgrade base` | PostgreSQL |
| Lint / types (API) | | `uv run ruff check . && uv run ruff format --check . && uv run mypy careerpilot` | |
| Web unit | `apps/web/src/**/*.test.tsx` | `cd apps/web && npm test` | |
| Lint / types (web) | | `npm run lint && npm run typecheck` | |
| Web build | | `npm run build` | |
| End-to-end (browser) | `apps/web/e2e/journey.spec.ts` | see below | Running web + API + PostgreSQL + Mailpit |

Without `uv` installed globally, use `python -m uv`, or run the venv interpreter directly
(`.venv/Scripts/python -m pytest` on Windows).

## Mock vs. real-provider tests

All automated tests use `MockLLMProvider` (deterministic, labeled `mock-deterministic-v1`) or scripted providers
(`tests/unit/test_ai_client.py`). **No test calls a real AI provider.** The `real_provider` pytest marker is
reserved for opt-in smoke tests that cost money; none are committed yet. To smoke-test Anthropic manually:

```bash
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... uv run python -c "
from careerpilot.ai.providers import AnthropicLLMProvider, LLMRequest
from careerpilot.ai.schemas import JobExtraction
p = AnthropicLLMProvider()
r = p.complete(LLMRequest(operation='job_extraction', system='Extract.', prompt='Need 3+ years Python and SQL.', schema=JobExtraction))
print(JobExtraction.model_validate_json(r.text))"
```

## End-to-end journey

The Playwright spec drives the real UI through: employer and candidate registration with email verification read
from Mailpit, company creation, admin approval, job creation and publication, resume upload, fact review,
recommendations and match explanation, cover-letter drafting, candidate approval and submission, employer
shortlisting, the candidate seeing the confirmed status, data export and account deletion.

```bash
docker compose up -d postgres redis mailpit
cd services/api
export DATABASE_URL=postgresql+psycopg://careerpilot:careerpilot@127.0.0.1:5432/careerpilot
uv run alembic upgrade head && uv run python -m careerpilot.cli seed-skills
CAREERPILOT_ADMIN_PASSWORD='choose a passphrase' uv run python -m careerpilot.cli create-admin admin@example.com "Platform Admin"
EMAIL_PROVIDER=smtp SMTP_HOST=127.0.0.1 SMTP_PORT=1025 FRONTEND_URL=http://localhost:3000 \
  uv run uvicorn careerpilot.main:app --host 127.0.0.1 --port 8000 &
cd ../../apps/web
API_INTERNAL_URL=http://127.0.0.1:8000 npm run build && API_INTERNAL_URL=http://127.0.0.1:8000 npx next start -p 3000 &
npx playwright install chromium
E2E_ADMIN_EMAIL=admin@example.com E2E_ADMIN_PASSWORD='choose a passphrase' npm run e2e
```

## Test data

All fixtures are synthetic (`tests/conftest.py`: `RESUME_TEXT`, `make_pdf`, `make_docx`; `apps/web/e2e/fixtures/resume.pdf`
generated from the same text). No real personal data is used.

## Regenerating OpenAPI

```bash
cd services/api && uv run python -c "import json,os; os.environ.setdefault('DATABASE_URL','sqlite:///:memory:'); from careerpilot.main import create_app; json.dump(create_app().openapi(), open('../../docs/openapi.json','w'), indent=1)"
```

Latest recorded results are in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).
