# Data model

PostgreSQL 17 with pgvector. Every table has a UUID primary key `id` and `created_at`/`updated_at`
(timestamptz). The schema is created by Alembic migration `services/api/alembic/versions/0001_initial_schema.py`;
CI verifies `alembic check` (models and migrations match) and a downgrade/upgrade round trip.
ER diagram: [`diagrams/er-diagram.mmd`](diagrams/er-diagram.mmd).

Enums are stored as constrained `VARCHAR` (`native_enum=False`) so values can be added without `ALTER TYPE`.

## Deletion behavior

Deleting a user (`POST /privacy/delete-account`) cascades through every FK marked **CASCADE** below. Stored files
are deleted from object storage first. `audit_events`, `data_deletion_requests` keep only the opaque user id (no
FK). Columns marked **SET NULL** keep the row but drop the link (for example a company outlives its creator).
Soft deletion is not used, except `documents.deleted_at`, which is reserved for a future retention grace period.

## Tables

### Identity

| Table | Purpose / important fields |
| --- | --- |
| `users` | `email` (unique, lower-cased), `full_name`, `status` (active/suspended/deleted), `email_verified_at`, `last_login_at`, `mfa_enabled` (reserved) |
| `user_roles` | (`user_id` CASCADE, `role` candidate/employer/admin), unique per pair |
| `user_credentials` | `password_hash` (Argon2id), `password_changed_at`. Separate so profile queries never load hashes |
| `user_sessions` | `token_hash`, `csrf_hash` (SHA-256), `expires_at`, `last_seen_at`, `revoked_at`, `user_agent`, `ip_prefix` (/24 or /48) |
| `email_verification_tokens` | `token_hash` (unique), `email` being verified, `expires_at`, `consumed_at` |
| `password_reset_tokens` | `token_hash`, `expires_at`, `consumed_at` |

### Candidate

| Table | Purpose / important fields |
| --- | --- |
| `candidate_profiles` | 1:1 with user. `headline`, `summary`, `location_city`, `location_country` (ISO-2), `phone`, `links`, `years_experience_confirmed` (overrides computed), `onboarding_completed` |
| `candidate_preferences` | `desired_titles`, `employment_types`, `work_arrangements`, `preferred_locations`, `willing_to_relocate` (tri-state), `min_salary` + `salary_currency`, `available_from` |
| `candidate_skills` | `name`, `name_normalized` (unique per profile), `skill_id` → taxonomy (SET NULL), `years`, `status` (fact status), `evidence` (resume id + quote) |
| `candidate_experiences` | `title`, `company`, dates, `is_current`, `description`, `status`, `source_resume_id` (SET NULL) |
| `candidate_educations` | `institution`, `degree`, `field_of_study`, dates, `status`, `source_resume_id` |
| `skills_taxonomy` | `canonical_name`, `slug` (unique), `category`, `aliases` (JSONB), `is_active`. Seeded by `cli seed-skills` (134 skills) |

Fact status: `stated` (explicit in source), `inferred`, `user_confirmed`, `rejected`. Only `user_confirmed` rows
are used for matching and generation.

### Documents

| Table | Purpose / important fields |
| --- | --- |
| `documents` | Object metadata only (no binaries): `storage_key` (random, unique), sanitized `original_filename`, `mime_type`, `size_bytes`, `sha256`, `scan_status` |
| `resumes` | `document_id` (1:1, CASCADE), `label`, `is_primary`, `status` (queued/processing/completed/failed), safe `status_detail`, `extraction_method`, `page_count`, `extracted_text`, `extraction` (validated JSON), `schema_version`, `model_name`, `processed_at` |
| `extracted_profile_facts` | Provenance per field: `fact_type`, `value`, `source_text`, `source_section`, `confidence`, `method`, `status`, `schema_version`, `applied_at` |
| `resume_versions` | Tailored versions (schema ready; feature planned): `version_number`, `content`, `unsupported_claims`, `approved_at` |

### Companies and jobs

| Table | Purpose / important fields |
| --- | --- |
| `companies` | `name`, `slug`, `website`, `email_domain`, profile fields, `verification_status` (unverified/pending/verified/rejected/suspended), `verified_at` |
| `company_members` | (`company_id`, `user_id`) unique, `role` owner/recruiter/viewer |
| `company_verification_records` | Each request: `status`, `method`, `signals` (domain match, free mailbox...), `evidence_note`, reviewer, decision reason |
| `jobs` | Full posting fields, `status` (draft/pending_review/published/paused/closed/archived), `published_at`, `closed_at`, `external_apply_url`, `version` (optimistic locking). CHECK constraints: salary range, experience range, openings ≥ 1. Indexes on status/published_at and search filters |
| `job_skills` | `name`, `name_normalized`, `requirement` required/preferred, `min_years` |

### Matching

| Table | Purpose / important fields |
| --- | --- |
| `embeddings` | (`owner_type`, `owner_id`, `model`) unique; `dimensions`, `content_hash`, `vector` (pgvector, dimension-less so models can coexist) |
| `job_recommendations` | Latest score per (candidate, job): `relevance_score`, `eligibility`, `components`, `explanation`, `algorithm_version` |
| `recommendation_events` | Consented feedback: `event_type`, `algorithm_version`, `relevance_score` |
| `saved_jobs` | (`user_id`, `job_id`) unique |

### Applications

| Table | Purpose / important fields |
| --- | --- |
| `applications` | (`candidate_user_id`, `job_id`) unique; `company_id`; `resume_id` (SET NULL); `status`; `submitted_at`; `first_viewed_at` (set when an authorized member first opens it); `candidate_snapshot` (confirmed facts at submission); `relevance_snapshot`; `candidate_approved_at` |
| `application_documents` | Immutable submitted copies (`cover_letter`), `generated_by`, `unsupported_claims` |
| `application_status_history` | `from_status`, `to_status`, `actor_user_id`, `actor_type`, `note` (employer-only) |
| `cover_letter_drafts` | Versioned drafts per (owner, job) with claims and prompt version |
| `interviews` | `starts_at`, `duration_minutes`, `location_or_link`, `status` |
| `idempotency_keys` | (`user_id`, `scope`, `key`) unique, `request_hash`, `resource_id` |

### Platform

| Table | Purpose / important fields |
| --- | --- |
| `notifications` | (`user_id`, `dedupe_key`) unique, `kind`, `title`, `body`, `link`, `read_at`, `email_status` (not_sent/sent/failed/skipped, the real provider outcome) |
| `notification_preferences` | Email toggles |
| `consent_records` | Append-only: `consent_type`, `granted`, `policy_version`, `source` |
| `data_deletion_requests` | `user_id` (no FK), `status`, `summary` |
| `audit_events` | `actor_user_id`, `action`, `target_type`, `target_id`, redacted `metadata`, `request_id`, `ip_prefix` |
| `background_tasks` | `name`, `entity_type/id`, `status`, `attempts`, safe `last_error`, `finished_at` |
| `ai_usage_records` | `provider`, `model`, `operation`, `prompt_version`, tokens, `estimated_cost_usd`, `latency_ms`, `success`, `error_code` |
| `reports` | Abuse reports: `target_type`, `target_id`, `reason`, `details`, `status` |
| `moderation_actions` | Admin actions with `reason`, linked to reports |

## Retention (initial policy, requires legal review)

See [PRIVACY_AND_RETENTION.md](PRIVACY_AND_RETENTION.md).
