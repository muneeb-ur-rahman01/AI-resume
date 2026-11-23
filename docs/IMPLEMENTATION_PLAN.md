# Implementation plan and feature checklist

Status legend: **verified** (implemented and covered by passing automated tests), **implemented** (code exists,
not covered end-to-end by tests), **partial**, **planned**.

Repository inspection on 2026-11-17 found an empty directory, so this is a greenfield build. The first increment
is the end-to-end vertical slice from spec section 32.

## Phases

| Phase | Scope | Status |
| --- | --- | --- |
| 1. Planning | Plan, architecture, diagrams, ADRs, checklist | Done |
| 2. Foundation | Monorepo, config validation, logging, health, Docker Compose, CI | Done (full container stack not yet run end-to-end) |
| 3. Identity + DB | Schema, migration, auth, verification, reset, sessions, RBAC, isolation tests | Done |
| 4. Core product | Profiles, companies, verification, jobs, resumes, worker, applications | Done for the slice |
| 5. AI pipeline | Extraction, OCR fallback, job parsing, taxonomy, embeddings, retrieval, ranking, explanations, cover letters, factuality checks, mock | Done except resume tailoring and the evaluation harness |
| 6. UI | Design tokens, components, candidate/employer/admin screens, states, a11y basics | Done for the slice |
| 7. Quality + security | Unit/API/security tests, e2e, scans | Tests done; external scans run in CI only |
| 8. Docs + release readiness | README, docs, status report | Done; restore drill and full container run outstanding |

## Vertical slice (spec section 32)

| # | Feature | Status |
| --- | --- | --- |
| 1 | Candidate registration + email verification | verified (API tests + e2e) |
| 2 | Candidate profile + resume upload | verified |
| 3 | PDF/DOCX text extraction | verified |
| 4 | Structured resume parsing (LLM with schema; heuristic fallback) | verified with mock provider; Anthropic adapter implemented, not live-tested |
| 5 | Employer registration + job publishing | verified |
| 6 | Matching + explainable recommendations | verified |
| 7 | Cover-letter generation with claim checks | verified (mock provider) |
| 8 | Candidate-approved idempotent submission | verified |
| 9 | Employer application review | verified |
| 10 | Application tracking | verified |
| 11 | Automated tests + documentation | verified |

## Full feature checklist

| Area | Feature | Status |
| --- | --- | --- |
| Auth | Register, verify, login/logout, sessions list/revoke | verified |
| Auth | Password reset, change password, lockout, rate limits, CSRF, enumeration protection | verified |
| Auth | Email change flow, OAuth/OIDC, MFA (TOTP) | planned |
| Candidate | Profile, skills, experience, education, preferences editing | verified (API), implemented (UI) |
| Candidate | Resume library, processing status, retry, delete, download | verified |
| Candidate | Fact review with provenance, no silent overwrite | verified |
| Candidate | Recommendations, match explanation, dismiss | verified |
| Candidate | Job search + filters (non-AI) | verified |
| Candidate | Saved jobs | implemented (API); UI page planned |
| Candidate | Cover letter generate/edit/version | verified |
| Candidate | Resume tailoring | planned |
| Candidate | Applications list/detail/timeline/withdraw | verified |
| Candidate | Interview prep, career guidance, skill-gap analysis | planned |
| Candidate | Notifications center + preferences | implemented |
| Candidate | Privacy consents, export, delete | verified |
| Employer | Company create/edit, verification request | verified |
| Employer | Team invitations, role management | planned |
| Employer | Job create/edit/publish/pause/close/archive, optimistic locking | verified |
| Employer | AI-assisted requirement parsing (advisory) | verified (mock) |
| Employer | Applicant inbox, detail, resume download, status changes, interview scheduling | verified (interviews: implemented) |
| Employer | Analytics | partial (counts endpoint) |
| Admin | Verification queue, user suspend/reinstate, reports moderation, failed tasks retry, audit search, metrics, taxonomy | implemented; suspension and verification verified |
| Platform | Background tasks + tracking, Celery worker | implemented (inline mode verified) |
| Platform | Notifications with dedupe + truthful email status | implemented |
| Platform | Audit log | verified |
| Platform | Billing readiness | planned |
| Platform | Retention purge jobs, scheduled tasks | planned |
| AI | Evaluation harness and benchmarks | planned |
| Ops | Dockerfiles, Compose, CI | implemented (CI not yet run on GitHub) |
| Design | Tokens, design system docs, component inventory | implemented; wireframe images planned |

Next increments are listed in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md#recommended-next-steps).
