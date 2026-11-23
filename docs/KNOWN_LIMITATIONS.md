# Known limitations

Everything below is **not implemented** or **only partly implemented** in the current vertical slice.

## Product scope

- Resume tailoring (the `resume_versions` table exists; no generation or editor yet), PDF/DOCX export of
  generated documents.
- Interview preparation, career guidance assistant, skill-gap analysis pages.
- Onboarding wizard as a dedicated stepper (the dashboard checklist guides the same steps).
- Team invitations and role management for companies (one owner per company; `recruiter`/`viewer` roles exist in
  the model and authorization but cannot be assigned through the API yet).
- Candidate-employer messaging; interview reminders by email; new-recommendation emails.
- Auto-apply (deliberately not built; every submission needs explicit confirmation).
- External ATS integrations (external jobs only show a link).
- Billing / subscriptions / quotas.
- Help and support pages; saved-jobs page in the UI (the API exists).
- Job moderation queue UI (`JOB_MODERATION_ENABLED` sends jobs to `pending_review`, but no admin approval
  endpoint exists yet, so keep it off).

## Security / identity

- MFA (TOTP), OAuth/OIDC login, email-change verification flow.
- CSP for the Next.js app allows `'unsafe-inline'` scripts (nonce middleware not added yet).
- Rate limiting falls back to per-process memory without Redis.
- No external penetration test.

## AI / data

- The Anthropic adapter is implemented per the official SDK documentation but **was not exercised against the
  live API** (no key was used during development).
- The default embedder is lexical (feature hashing); semantic quality needs a real embedding model.
- Ranking weights are uncalibrated; no evaluation dataset or benchmark results exist yet.
- OCR requires installing Tesseract and the `ocr` extra; it is untested in CI.
- ClamAV integration is implemented but untested against a live daemon.
- No retention purge jobs (sessions, tokens, audit, AI usage); no Celery beat schedule yet.
- No vector ANN index yet (exact ordering is fine at small scale).

## Operations / docs

- Docker Compose was validated (`docker compose config`), and the `postgres`, `redis` and `mailpit` services ran
  during development. The full containerized stack (`api`, `worker`, `web`, `minio`) was **not** built and run
  end-to-end in this session.
- Mermaid diagrams are committed as `.mmd` sources only; no SVG/PNG renders.
- `/design` has tokens, specifications, text wireframes and real app screenshots, but no wireframe image files
  and no Figma file. Mobile screenshots exist only for the landing page and the candidate dashboard.
- No automated accessibility (axe) scan or manual screen-reader pass yet.
- Restore drill not yet performed; OpenTelemetry tracing and error-tracking integrations not wired.
- No license selected.
