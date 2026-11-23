# Contributing

1. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and the relevant ADRs.
2. Branch from `main`; keep changes small and focused.
3. Before opening a PR:
   - API: `uv run ruff check . && uv run ruff format --check . && uv run mypy careerpilot && uv run pytest`
   - Web: `npm run lint && npm run typecheck && npm test && npm run build`
   - Schema changes: add an Alembic migration and make sure `alembic check` is clean.
4. New endpoints must have: a DTO with `extra="forbid"`, an authorization check (role + ownership/tenant), safe
   errors, pagination for collections, tests for success, unauthorized and cross-tenant access, and an update to
   docs/API_GUIDE.md and docs/openapi.json.
5. AI changes must bump the prompt/schema version, keep output validated, and never let model output change
   permissions or state directly.
6. Never commit secrets or real personal data. Test fixtures must be synthetic.
7. Update CHANGELOG.md and, when status changes, docs/IMPLEMENTATION_STATUS.md.
