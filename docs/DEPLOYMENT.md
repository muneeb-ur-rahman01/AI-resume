# Deployment

**Status: no production deployment has been performed.** This guide describes the intended topology and the
steps that are required. Automatic production deployment is intentionally not configured in CI.

## Environments

| Environment | Purpose | Notes |
| --- | --- | --- |
| development | Local work | `docker compose up` or local processes; mock AI, Mailpit, MinIO allowed |
| staging | Pre-release verification with production-like config | Real providers with test credentials; same config safety checks as production |
| production | Live users | Managed PostgreSQL/Redis/S3, real SMTP, secret manager, TLS |

`config.Settings` refuses to start staging/production with a default or short `SECRET_KEY`, `DEBUG=true`,
`COOKIE_SECURE=false`, `LLM_PROVIDER=mock`, `EMAIL_PROVIDER=console`, or (production) `STORAGE_PROVIDER=local`.

## Topology

See [diagrams/deployment.mmd](diagrams/deployment.mmd): TLS load balancer → `web` (Next.js standalone, 2+
replicas) → `api` (FastAPI/Uvicorn, 2+ replicas) on a private network; `worker` (Celery) autoscaled on queue
depth; managed PostgreSQL 17 with pgvector and point-in-time recovery; managed Redis; private S3 bucket with SSE;
transactional email provider; logs/metrics shipped to your observability stack.

## Images

```bash
docker build -t careerpilot-api services/api                    # API and worker (same image)
docker build --build-arg API_INTERNAL_URL=http://api:8000 -t careerpilot-web apps/web
```

Both images run as non-root users. The worker uses the API image with
`celery -A careerpilot.worker worker --loglevel=INFO`.

## Release procedure

1. CI green on the release commit (lint, types, tests on SQLite and PostgreSQL, migrations check, audits, image build).
2. Back up the database (or confirm a recent PITR point).
3. Run migrations as a one-off job with the migration DB role: `alembic upgrade head`.
4. Run `python -m careerpilot.cli seed-skills` (idempotent).
5. Roll out `api` and `worker`, then `web`. Health checks: `GET /api/v1/health/live` (liveness) and
   `/api/v1/health/ready` (readiness: DB, Redis).
6. Smoke test: register → verify → login; job search; resume upload on a test account.

Migrations should stay backward compatible for one release (expand → migrate → contract), so old pods keep
working during rollout.

## Required configuration (production)

`ENVIRONMENT=production`, `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `TASK_MODE=celery`, `FRONTEND_URL`,
`CORS_ORIGINS`, `COOKIE_SECURE=true`, `EMAIL_PROVIDER=smtp` + `SMTP_*` + `EMAIL_FROM`,
`STORAGE_PROVIDER=s3` + `S3_*`, `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` (or explicitly accept mock),
optional `MALWARE_SCANNER=clamav`, `OCR_PROVIDER=tesseract`. See `.env.example`.

## Hardening checklist

- [ ] TLS everywhere; HSTS enabled (automatic with `COOKIE_SECURE=true`)
- [ ] `api` reachable only from `web`/internal network; `/api/docs` disabled (automatic in staging/production)
- [ ] DB roles: migration (DDL) vs. app (DML only)
- [ ] S3 bucket: block public access, SSE, lifecycle rules, scoped IAM
- [ ] Redis with auth/TLS; not internet-exposed
- [ ] Log retention and PII handling reviewed
- [ ] Backups and restore drill done (BACKUP_AND_RECOVERY.md)
- [ ] Admin access restricted by network until MFA exists
- [ ] Provider data-processing agreements in place (PRIVACY_AND_RETENTION.md)
