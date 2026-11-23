# API guide

- Base path: `/api/v1`. Interactive docs (non-production only): `http://localhost:8000/api/docs`.
- Machine-readable contract: [`docs/openapi.json`](openapi.json). Regenerate it with the command in
  [TESTING.md](TESTING.md#regenerating-openapi). It is the source of truth for request and response schemas.
- All bodies are JSON except resume upload (`multipart/form-data`). Unknown fields are rejected (`422`).

## Conventions

**Authentication.** `POST /auth/login` sets `cp_session` (HttpOnly) and `cp_csrf` (readable) cookies. Every
authenticated `POST/PUT/PATCH/DELETE` must send `X-CSRF-Token: <cp_csrf value>`. Requests with a non-allow-listed
`Origin` are rejected.

**Errors.**

```json
{"error": {"code": "duplicate_application", "message": "You have already applied to this job.",
           "details": {}, "request_id": "8a5c..."}}
```

| HTTP | Typical codes |
| --- | --- |
| 400 | `invalid_token`, `bad_request` |
| 401 | `unauthenticated`, `session_expired`, `invalid_credentials`, `reauthentication_failed` |
| 403 | `forbidden`, `csrf_failed`, `origin_not_allowed`, `email_not_verified`, `account_inactive`, `company_not_verified` |
| 404 | `not_found` (also returned for resources owned by someone else) |
| 409 | `conflict`, `duplicate_application`, `invalid_transition`, `invalid_state`, `version_conflict`, `idempotency_key_reused`, `external_application_required` |
| 413 | `file_too_large`, `payload_too_large` |
| 422 | `validation_failed`, `document_rejected`, `unsupported_file_type`, `file_type_mismatch`, `suspicious_document`, `encrypted_document`, `consent_required`, `confirmation_required`, `profile_incomplete` |
| 429 | `rate_limited` (with `Retry-After`), `account_locked` |
| 503 | `service_unavailable`, `ai_unavailable` |

**Pagination.** `page` (≥1) and `page_size` (capped per endpoint, 50-200). Responses: `{items, total, page, page_size}`.

**Idempotency.** `POST /candidate/applications` requires `Idempotency-Key` (8-100 chars). Replaying the same key
and body returns `200` with the original application and `Idempotent-Replayed: true`. Reusing a key with a
different body returns `409 idempotency_key_reused`.

## Endpoints

Roles: **public**, **any** (any signed-in user), **C** candidate, **E** employer (plus company membership
checks), **A** admin. Ownership: candidate routes act only on the caller's data; employer routes require
membership in the owning company (`write` = owner/recruiter); non-members receive 404.

### Auth (`/auth`)

| Method | Path | Auth | Notes / rate limit |
| --- | --- | --- | --- |
| POST | `/auth/register` | public | Generic 202 for new and existing emails; roles `candidate`/`employer` only; 10/h per IP |
| POST | `/auth/verify-email` | public | Single-use, 24 h token; 20/h per IP |
| POST | `/auth/resend-verification` | public | Generic 202; 5/h per IP and per email |
| POST | `/auth/login` | public | 30/5 min per IP; 10 failures per account lock it for 15 min; unverified accounts get 403 |
| POST | `/auth/logout` | any | Revokes the current session |
| GET | `/auth/me` | any | |
| GET | `/auth/sessions` | any | Active sessions; `current` flag |
| DELETE | `/auth/sessions/{id}` | any | Own sessions only |
| POST | `/auth/sessions/revoke-others` | any | |
| POST | `/auth/forgot-password` | public | Generic 202; 5/h per IP and per email |
| POST | `/auth/reset-password` | public | Single-use 30 min token; revokes all sessions |
| POST | `/auth/change-password` | any | Requires the current password; revokes other sessions |

### Candidate (`/candidate`, role C)

| Method | Path | Notes |
| --- | --- | --- |
| GET/PUT | `/candidate/profile` | Basics; links must be http(s); `years_experience_confirmed` overrides the computed value |
| PUT | `/candidate/preferences` | Titles, employment types, arrangements, relocation, minimum salary (currency required) |
| POST, DELETE | `/candidate/skills`, `/candidate/skills/{id}` | Normalized against the taxonomy |
| POST, PUT, DELETE | `/candidate/experiences[/{id}]` | Date ordering validated |
| POST, DELETE | `/candidate/educations[/{id}]` | |
| GET, POST | `/candidate/resumes` | Upload: PDF/DOCX ≤ `MAX_UPLOAD_MB`, 20/h; processing is asynchronous |
| GET, PATCH, DELETE | `/candidate/resumes/{id}` | Detail includes extracted facts and warnings; PATCH sets label/primary |
| POST | `/candidate/resumes/{id}/retry` | Re-runs processing |
| POST | `/candidate/resumes/{id}/review` | `{accept: [fact ids], reject: [...], overwrite_text_fields}` |
| GET | `/candidate/resumes/{id}/download` | Streams (local) or 307 to a 5-minute presigned URL (S3) |
| GET | `/candidate/recommendations` | `limit` ≤ 50, `include_ineligible` |
| GET | `/candidate/jobs/{id}/match` | Explanation for one job |
| POST | `/candidate/recommendation-events` | `click`/`save`/`dismiss`; recorded only with consent (dismiss always) |
| GET, PUT, DELETE | `/candidate/saved-jobs[/{job_id}]` | |
| GET, POST | `/candidate/jobs/{id}/cover-letters` | List versions / save a manual version (claims re-checked) |
| POST | `/candidate/jobs/{id}/cover-letters/generate` | Requires `ai_processing` consent; 30/h |
| GET | `/candidate/applications/preview?job_id=` | Everything that will be shared |
| POST | `/candidate/applications` | `confirm: true` + `Idempotency-Key`; 409 for duplicates or external jobs |
| GET | `/candidate/applications`, `/candidate/applications/{id}` | Employer notes are not exposed |
| POST | `/candidate/applications/{id}/withdraw` | From submitted/shortlisted/interview/offer |

### Employer (`/employer`, role E)

| Method | Path | Notes |
| --- | --- | --- |
| GET, POST | `/employer/companies` | One owned company per user (team invitations planned) |
| PATCH | `/employer/companies/{id}` | write |
| GET, POST | `/employer/companies/{id}/verification` | POST: owners only; records signals; status `pending` |
| GET | `/employer/companies/{id}/analytics` | Counts by job and application status |
| GET, POST | `/employer/companies/{id}/jobs` | Create drafts (write) |
| POST | `/employer/jobs/parse` | AI-suggested requirements, not saved; 30/h |
| GET, PUT | `/employer/jobs/{id}` | PUT only in draft/paused/pending_review; `expected_version` for optimistic locking |
| POST | `/employer/jobs/{id}/status` | State machine; publishing requires a verified company (configurable) |
| GET | `/employer/jobs/{id}/applications` | Excludes withdrawn |
| GET | `/employer/applications/{id}` | Records `first_viewed_at`; includes allowed transitions |
| POST | `/employer/applications/{id}/status` | `shortlisted`/`interview`/`offer`/`rejected`/`hired` per state machine; notifies the candidate |
| POST | `/employer/applications/{id}/interviews` | Future time only |
| GET | `/employer/applications/{id}/resume` | Audited download |

### Admin (`/admin`, role A; every mutation audited)

`GET /admin/companies?status=`, `POST /admin/companies/{id}/verification`, `POST /admin/companies/{id}/suspend`,
`GET /admin/users`, `POST /admin/users/{id}/suspend|reinstate`, `GET /admin/audit-events`,
`GET /admin/reports`, `POST /admin/reports/{id}/resolve`, `GET /admin/tasks`, `POST /admin/tasks/{id}/retry`,
`GET /admin/metrics`, `GET|POST /admin/skills`.

### Public, notifications, privacy

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/jobs` | public | `q`, `employment_type`, `work_arrangement`, `country`, `skill`, `min_salary`, `sort=newest|salary`, pagination |
| GET | `/jobs/{id}` | public | Published, unexpired jobs from non-suspended companies |
| POST | `/jobs/{id}/reports` | any | `fraud|discriminatory|misleading|abusive|other` |
| GET | `/notifications` | any | `unread_only` |
| POST | `/notifications/{id}/read`, `/notifications/read-all` | any | |
| GET/PUT | `/notifications/preferences` | any | |
| GET/PUT | `/privacy/consents` | any | `ai_processing`, `recommendation_tracking`; append-only log |
| GET | `/privacy/export` | any | Full JSON export; 10/h |
| POST | `/privacy/delete-account` | any | Requires the password; deletes files and data |
| GET | `/health/live`, `/health/ready` | public | Ready checks DB (and Redis if configured) and reports whether AI is mocked |
