# Operations runbook

All commands run from `services/api` with the target environment's variables loaded.

## Health

- Liveness: `GET /api/v1/health/live`. Readiness: `GET /api/v1/health/ready` (database, Redis; reports `ai.mock`).
- Logs are JSON on stdout with `request_id`. Clients receive the same id in `X-Request-ID` and in error bodies.
- Admin console → metrics: users, published jobs, pending verifications, open reports, failed tasks, 7-day AI
  usage and estimated cost.

## Failed background jobs

1. Admin console → *Failed background tasks* (or `GET /api/v1/admin/tasks?status=failed`).
2. Check `last_error` (exception class only) and correlate in logs by `task_id`.
3. Retry from the console (`POST /admin/tasks/{id}/retry`) once the cause is fixed. Candidates can also retry
   from the resume page.
4. Celery is configured with `acks_late` and `reject_on_worker_lost`, so a crashed worker's task is re-delivered.

## AI provider outage

- Symptoms: `ai_usage_records.error_code` in (`timeout`, `unavailable`, `rate_limited`, `circuit_open`), 503
  `ai_unavailable` responses.
- Behavior: resume processing falls back to heuristics (with a visible note); job parsing and cover letters return
  503 with manual alternatives; search and recommendations are unaffected.
- Actions: check the provider status page; reduce `LLM_MAX_CONCURRENCY`; if prolonged, set `LLM_PROVIDER` to
  another configured provider. Do **not** switch production to `mock`; it is refused by config.
- Afterwards, re-run extraction for affected resumes (`POST /candidate/resumes/{id}/retry`, or admin retry).

## Revoke sessions

```sql
-- one user
UPDATE user_sessions SET revoked_at = now() WHERE user_id = '<uuid>' AND revoked_at IS NULL;
-- everyone (suspected session compromise)
UPDATE user_sessions SET revoked_at = now() WHERE revoked_at IS NULL;
```

Suspending a user in the admin console also revokes their sessions.

## Rotate secrets

| Secret | Procedure | Effect |
| --- | --- | --- |
| `SECRET_KEY` | Generate a new value, update the secret manager, redeploy | No user impact (sessions are random tokens) |
| DB password | Create the new credential, update, redeploy, drop the old one | Rolling |
| S3 keys | Create a second key, deploy, deactivate the old one | Rolling |
| SMTP / LLM / embedding keys | Issue new, deploy, revoke old at the provider | Brief failures fall back as above |
| Suspected token leak | Revoke all sessions (SQL above); invalidate outstanding reset/verification tokens: `UPDATE password_reset_tokens SET consumed_at=now() WHERE consumed_at IS NULL;` | Users sign in again |

## Moderation

Reports appear in the admin console. Actions: dismiss, pause job, close job; suspend company (pauses all its
published jobs); suspend/reinstate users. Every action is audited with a reason.

## Create an administrator

```bash
python -m careerpilot.cli create-admin admin@example.com "Full Name"   # prompts for a password
```

## Data deletion requests

Self-service via Settings. Check `data_deletion_requests` for `status='failed'` (object-storage deletion
failures) and delete the listed objects manually.
