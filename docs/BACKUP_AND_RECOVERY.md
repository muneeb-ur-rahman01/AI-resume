# Backup and recovery

**Status:** procedures documented; **a restore drill has not been performed** in this repository.

## What to back up

| Store | Method | Target RPO / RTO (initial, unmeasured) |
| --- | --- | --- |
| PostgreSQL | Managed PITR (WAL) + daily logical dump | RPO ≤ 15 min, RTO ≤ 4 h |
| Object storage | Bucket versioning + cross-region replication | RPO ≤ 1 h |
| Redis | Not backed up (rate-limit counters and queue only; tasks are re-runnable) | — |
| Configuration | Secret manager versioning; IaC in git | — |

## Logical backup and restore (PostgreSQL)

```bash
pg_dump --format=custom --no-owner "$DATABASE_URL_ADMIN" > careerpilot-$(date +%F).dump
# restore into an empty database that has the vector extension available
createdb careerpilot_restore
psql careerpilot_restore -c "CREATE EXTENSION IF NOT EXISTS vector"
pg_restore --no-owner --dbname=careerpilot_restore careerpilot-YYYY-MM-DD.dump
DATABASE_URL=postgresql+psycopg://.../careerpilot_restore alembic current   # expect head
```

Local dev (Docker Compose):

```bash
docker compose exec postgres pg_dump -U careerpilot -Fc careerpilot > dev.dump
docker compose exec -T postgres pg_restore -U careerpilot -d careerpilot --clean < dev.dump
```

## Restore drill (quarterly)

1. Restore the latest PITR point into an isolated instance.
2. Run `alembic current`, `GET /health/ready` against a staging API pointed at it, and sample queries.
3. Verify that object keys referenced by `documents.storage_key` exist in the restored bucket.
4. Record the measured RPO/RTO in this file.

## Deleted-user consistency

Backups taken before an account deletion still contain that user's data. After restoring, re-apply completed
deletions: for each `data_deletion_requests` row with `completed_at` later than the restore point, delete the
user (if present) and their objects.
