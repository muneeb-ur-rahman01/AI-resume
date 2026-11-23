# Incident response

## Severity

| Level | Examples | Response |
| --- | --- | --- |
| SEV1 | Confirmed personal-data exposure, credential compromise, full outage | Immediate; incident lead + security + legal |
| SEV2 | Partial outage, AI provider down, failing uploads, suspected exposure | Within 1 hour |
| SEV3 | Degraded feature, elevated errors | Next business day |

## Roles

Incident lead (coordinates, decides), operator (executes runbook steps), communications (users/regulators),
scribe (timeline). Record the timeline in the incident ticket from the start.

## Suspected data exposure

1. **Contain.** Revoke affected sessions (OPERATIONS_RUNBOOK.md), rotate exposed secrets, block the access path
   (disable the endpoint behind the load balancer or suspend accounts).
2. **Preserve evidence.** Snapshot logs and the `audit_events` range; do not delete data.
3. **Scope.** Use `audit_events` (actor, action, target, request id), access logs and `application.resume_downloaded`
   events to determine which records were accessed.
4. **Assess obligations** with legal counsel. Regulatory notification deadlines can be short (for example 72 hours
   under GDPR).
5. **Notify** affected users and processors as required.
6. **Remediate** the root cause, add a regression test, update THREAT_MODEL.md.
7. **Post-incident review** within 5 business days (blameless).

## Other playbooks

- **AI provider outage or misbehavior**: OPERATIONS_RUNBOOK.md → AI provider outage. If outputs look manipulated
  (for example prompt injection succeeding), disable the provider and keep heuristic extraction.
- **Fraudulent employer wave**: set `REQUIRE_VERIFIED_COMPANY_TO_PUBLISH=true` (default) and
  `JOB_MODERATION_ENABLED=true`; suspend companies; review reports.
- **Database outage**: the API returns 503 `service_unavailable`; follow BACKUP_AND_RECOVERY.md if data is lost.
