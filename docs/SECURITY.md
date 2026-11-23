# Security

OWASP ASVS / Top 10 are the baseline. This page describes what is implemented and how to operate it. Report
suspected vulnerabilities privately to the maintainers. No public disclosure channel has been configured yet.

## Controls implemented

| Area | Control | Where |
| --- | --- | --- |
| Passwords | Argon2id (argon2-cffi RFC 9106 defaults), ≥12 chars, common/repetitive/email/name checks, rehash on login | `security/passwords.py` |
| Tokens | 32-byte random tokens; only SHA-256 stored; constant-time compare; atomic single-use consumption; 24 h verification / 30 min reset expiry; older reset tokens invalidated | `security/tokens.py`, `services/auth.py` |
| Sessions | Opaque token in `HttpOnly; SameSite=Lax` cookie (`Secure` when `COOKIE_SECURE=true`); absolute (7 d) and idle (24 h) expiry; revocation on logout, password change/reset, admin suspension; session list and remote sign-out | `services/auth.py`, `api/routes/auth.py` |
| CSRF | Per-session CSRF token (hash stored server-side) required in `X-CSRF-Token` for all authenticated unsafe methods, plus an Origin allow-list check | `api/deps.py` |
| Enumeration | Identical responses for register, forgot-password and resend for existing and unknown emails; generic login errors; dummy-hash verification for unknown accounts | `services/auth.py` |
| Rate limiting | Redis fixed window (memory fallback) for login (IP + account lockout), registration, verification, reset, uploads, AI generation, sensitive actions | `security/rate_limit.py` |
| Authorization | Role dependencies; ownership filters; `require_member()` for company data with 404 for outsiders; admin role only via CLI; no self-verification | `api/deps.py`, `services/companies.py` |
| Mass assignment | Request DTOs use `extra="forbid"`; server-controlled fields (status, roles, verification) are never accepted from clients | `api/schemas.py` |
| Input validation | Pydantic DTOs with lengths, enums, ranges, cross-field rules; pagination caps; 12 MB request body limit | `api/schemas.py`, `main.py` |
| Uploads | Size cap, extension allow-list, magic bytes, encrypted-PDF detection, PDFs with JavaScript/launch/embedded files rejected, DOCX zip-bomb and macro checks, sanitized display filename, random object keys, private storage, ownership-checked downloads, optional ClamAV (fails closed) | `services/documents.py` |
| SSRF | Server never fetches user URLs. Outbound integrations go through `assert_safe_outbound_url` (https, optional allow-list, blocks private/loopback/link-local/reserved) with redirects disabled | `security/urls.py` |
| XSS | React escapes all text; no `dangerouslySetInnerHTML`; JSON-only API; CSP on web and API; user links restricted to http(s) | `next.config.ts`, `main.py` |
| Headers | CSP, `X-Content-Type-Options`, `X-Frame-Options: DENY`, Referrer-Policy, Permissions-Policy, COOP, HSTS when secure cookies are on, `Cache-Control: no-store` on API | `main.py`, `next.config.ts` |
| Errors | Uniform error envelope with request id; no stack traces, SQL or provider text; DB outages return 503 | `errors.py` |
| Logging | JSON logs with request ids; keys matching password/token/secret/cookie/session/api_key are redacted; emails masked | `logging_config.py` |
| Audit | Security and admin actions recorded with actor, action, target, request id, truncated IP | `services/audit.py` |
| Prompt injection | Untrusted text wrapped in tags with explicit rules; schema-constrained outputs; post-hoc grounding; heuristic injection detection surfaces a warning; AI output never changes permissions or state | `ai/prompts.py`, `services/resumes.py` |
| Config safety | Staging/production refuse a default/short `SECRET_KEY`, debug, insecure cookies, mock AI, console email, and local storage (production) | `config.py` |
| Supply chain | Locked dependencies (`uv.lock`, `package-lock.json`); CI runs `pip-audit`, `npm audit`, gitleaks | `.github/workflows/ci.yml` |

## Security tests

`services/api/tests/security/test_authorization.py` and `tests/api/test_auth.py` cover: unauthenticated access,
role enforcement, cross-candidate IDOR (resume, application, attaching another user's resume), cross-company
isolation, self-verification, mass assignment, prompt injection in an uploaded resume, XSS/link payloads,
SQL-injection strings, pagination limits, suspension, CSRF, cross-origin blocking, token expiry and reuse,
lockout, registration rate limits, hashed token storage, and safe errors.

## Operating securely

- **Secrets**: inject through a secret manager. Rotate `SECRET_KEY`, DB, S3, SMTP and provider keys per the runbook.
  Rotating `SECRET_KEY` does not invalidate sessions; sessions are random tokens. Revoke them in bulk by setting
  `revoked_at` (see OPERATIONS_RUNBOOK.md).
- **Least privilege**: give the app DB role DML-only rights; run migrations with a separate role. Scope the S3
  credentials to one bucket with no public ACLs.
- **Admins**: create with `python -m careerpilot.cli create-admin`. MFA for admins is **not yet implemented**;
  restrict admin access by network until it is (see KNOWN_LIMITATIONS.md).

## Known gaps (tracked)

MFA/TOTP, OAuth/OIDC, email-change flow, nonce-based CSP for Next.js (currently `'unsafe-inline'` scripts),
per-user data-access logging for employer resume views beyond download audit, and an external penetration test.
See [THREAT_MODEL.md](THREAT_MODEL.md) and [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).
