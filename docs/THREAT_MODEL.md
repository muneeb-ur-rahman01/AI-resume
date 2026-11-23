# Threat model (STRIDE, initial)

Scope: web app, API, worker, PostgreSQL, Redis, object storage, email, LLM provider. Assets: candidate PII and
resumes, application data, employer company data, credentials/sessions, provider keys, platform reputation.

| # | Threat | STRIDE | Mitigations | Residual risk |
| --- | --- | --- | --- | --- |
| 1 | Credential stuffing / brute force | S | Argon2id, per-IP and per-account throttling, generic errors, lockout window | No MFA yet; no breached-password check |
| 2 | Session theft via XSS | S/I | HttpOnly cookies, React escaping, CSP, no HTML rendering of user content | CSP allows inline scripts (Next.js) |
| 3 | CSRF | T | Session-bound CSRF header, Origin allow-list, SameSite=Lax, JSON bodies | — |
| 4 | Account enumeration | I | Generic responses + timing equalization | Rate-limit responses can still be probed slowly |
| 5 | IDOR on resumes/applications | I/E | Owner filters; 404 for non-owners; tests for each route | New routes must follow the pattern (code review) |
| 6 | Cross-tenant employer access | I/E | `require_member()` everywhere; tests | — |
| 7 | Fake employer posting scam jobs | S/T | Admin verification before publishing (configurable), reports + moderation, suspension | Manual review capacity |
| 8 | Malicious upload (malware, zip bomb, macro, PDF JS) | T/E | Validation, size/expansion limits, macro/JS rejection, optional ClamAV, never executed | Parser vulnerabilities in pdfplumber/python-docx: keep dependencies patched |
| 9 | Prompt injection via resume/job text | T/E | Tagged untrusted input, strict schemas, grounding, AI cannot change state or permissions | Model may still mis-extract; candidate review required |
| 10 | Fabricated qualifications in AI drafts | T | Confirmed-facts-only prompts, unsupported-claim detection, mandatory approval | Detector is heuristic, not exhaustive |
| 11 | PII leakage to AI provider | I | Consent gate, minimal fields, no logging of prompts, provider DPA required | Provider-side retention depends on contract |
| 12 | PII in logs | I | Redaction of sensitive keys, email masking | Free-text exceptions could contain PII; review logging in new code |
| 13 | SSRF | I/E | No user-URL fetching; guard for outbound integrations | — |
| 14 | Duplicate/forged applications | T | Idempotency keys, DB unique constraint, explicit confirm flag | — |
| 15 | Admin abuse | E/R | CLI-only admin creation, audit log, no admin self-suspension | No MFA, no dual control |
| 16 | DoS (uploads, AI cost) | D | Body limits, upload/AI rate limits, concurrency semaphore, circuit breaker, cost records | No per-tenant budgets yet |
| 17 | Storage misconfiguration (public bucket) | I | Private bucket, presigned URLs (5 min), SSE | Requires correct IaC |
| 18 | Repudiation of status changes | R | Status history with actor + audit events | — |

Review this model whenever a new external integration, upload type or AI capability is added.
