# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/);
versioning: SemVer.

## [0.1.0] - 2026-11-17

First end-to-end vertical slice.

### Added

- FastAPI modular monolith with versioned `/api/v1` routes (89 operations), uniform error envelope, request ids,
  JSON logging with redaction, security headers, health probes.
- Identity: registration, single-use email verification, login/logout, password reset and change, session
  management, Argon2id, CSRF, Origin checks, rate limits, lockout, enumeration protection, CLI-only admin creation.
- Candidate profile, preferences, skills, experience, education; resume upload with validation, optional malware
  scan, private storage; asynchronous processing (PDF/DOCX, optional OCR); AI or heuristic extraction with
  provenance; fact review.
- Companies, verification requests with signals, admin decisions; jobs with a state machine, optimistic locking,
  and AI-suggested requirements.
- Hybrid retrieval (SQL + pgvector) and explainable `rules-v1` ranking; recommendations, match explanations,
  consented feedback events.
- Cover letters from confirmed facts with unsupported-claim detection and versioning.
- Idempotent, candidate-approved applications; employer review, status changes, interviews; notifications.
- Privacy: consents, JSON export, account deletion. Admin: moderation, suspension, failed-task retry, audit search,
  metrics, taxonomy.
- Provider interfaces with an Anthropic adapter, a deterministic mock, a hashing embedder and an OpenAI-compatible
  embedder.
- Next.js 16 UI for candidate, employer and admin flows with accessible components and design tokens.
- Alembic initial migration; Docker images; Docker Compose stack; GitHub Actions CI.
- Tests: 77 backend tests (SQLite and PostgreSQL), 7 web unit tests, a Playwright end-to-end journey.
- Documentation set, ADRs, Mermaid diagrams, OpenAPI snapshot, design system and screenshots.

### Fixed during development

- Circuit breaker counted provider outages as successes (caught by a unit test).
- `prompt_version` columns were too short for PostgreSQL (caught by running the suite on PostgreSQL).
- `create-admin` accepted email addresses the login endpoint rejects (caught by the e2e test).
