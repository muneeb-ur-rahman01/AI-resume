# Privacy and data retention

**This is not legal advice and does not claim compliance with any law.** It documents the technical behavior so
counsel can review it against applicable jurisdictions (for example GDPR/UK GDPR, CCPA/CPRA, PIPEDA, and local
employment law).

## Data collected

| Category | Fields | Purpose |
| --- | --- | --- |
| Account | email, name, password hash, roles, login timestamps | Authentication |
| Candidate profile | headline, summary, city/country, phone, links, skills, experience, education, preferences | Matching, applications |
| Resumes | original file (object storage), extracted text, structured extraction | Profile building, sharing with employers the candidate applies to |
| Applications | snapshot of confirmed profile at submission, cover letter, status history | Hiring workflow |
| Employer | company profile, membership, verification evidence notes | Employer verification |
| Operational | sessions (hashed tokens, user agent, truncated IP), audit events, AI usage (no prompt content), notifications | Security, abuse prevention, cost control |

Not collected: government IDs, photos, date of birth, gender, ethnicity, religion, health, disability, marital
status. Prompts instruct models not to extract such attributes, and matching never uses them.

## Consent

- `ai_processing` (asked at registration, changeable in Settings): required to send resume text or profile facts
  to the configured LLM provider or an external embedding provider. Without it, deterministic local extraction is
  used and AI drafting is disabled.
- `recommendation_tracking`: required to record click/save/apply feedback events used for offline evaluation.
- Consent changes are append-only (`consent_records`) with policy version and timestamp.

## Sharing

Employers see an application's candidate snapshot, cover letter, attached resume and contact email only for
applications submitted to their company. Third-party processors: LLM provider (if enabled), embedding provider
(if external), email provider, object storage, hosting. Each needs a data-processing agreement.

## Rights

| Right | Implementation |
| --- | --- |
| Access / portability | `GET /privacy/export` (JSON with account, profile, resumes and extracted text, applications, drafts, consents, notifications) |
| Rectification | Profile editor; extracted facts require confirmation and can be rejected |
| Erasure | `POST /privacy/delete-account` (password re-entry): deletes stored files and all user rows by cascade; records a `data_deletion_requests` entry and an audit event with the opaque id |
| Objection to AI processing | Toggle `ai_processing` off |

## Retention (initial proposal, to be confirmed)

| Data | Proposed retention | Status |
| --- | --- | --- |
| Account and profile | Until deletion; flag inactive accounts after 24 months | Deletion implemented; inactivity sweep **not implemented** |
| Resumes and extracted text | Until the candidate deletes them or the account | Implemented |
| Applications | Until candidate deletion; employers may need a legal retention period | Policy decision pending |
| Sessions | Expire after 7 days (idle 24 h); purge revoked/expired rows after 30 days | Purge job **not implemented** |
| Verification/reset tokens | Purge 7 days after expiry | **Not implemented** |
| Audit events | 1-2 years | Purge **not implemented** |
| AI usage records | 13 months (cost analysis) | Purge **not implemented** |
| Backups | 30-35 days PITR; deletions propagate as backups age out | Operational |

## Privacy-by-design notes

- Logs redact secrets and mask emails; prompts and model outputs are not logged.
- IP addresses are stored truncated (/24 IPv4, /48 IPv6).
- Object keys are random; downloads are ownership-checked; S3 URLs expire in 5 minutes.
- Only confirmed facts are sent for generation; only the needed text for extraction.
