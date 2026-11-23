# AI architecture

## Principles

1. AI produces **suggestions**, never decisions. Extracted facts must be confirmed by the candidate; parsed job
   requirements must be applied by the recruiter; cover letters must be approved before submission.
2. Deterministic code handles everything it can do reliably: skill normalization, date validation, experience
   arithmetic, eligibility, ranking, explanations, unsupported-claim detection.
3. Untrusted text (resumes, job descriptions, company text) is wrapped in tags and declared data. Model output is
   validated against strict schemas and never used for authorization or state changes.
4. Only confirmed, minimal data is sent to providers, and only with the candidate's `ai_processing` consent.

## Provider interfaces (`careerpilot/ai/providers.py`)

| Interface | Implementations | Notes |
| --- | --- | --- |
| `LLMProvider.complete(LLMRequest) -> LLMResponse` | `AnthropicLLMProvider`, `MockLLMProvider` | Configured by `LLM_PROVIDER`, `LLM_MODEL`, `LLM_EFFORT`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` |
| `EmbeddingProvider.embed(texts)` | `HashingEmbeddingProvider`, `OpenAICompatibleEmbeddingProvider` | `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `EMBEDDING_API_BASE` |
| Reranker | none (`RERANKER_PROVIDER=none`) | Add only when offline evaluation shows a benefit |
| OCR | `ocr_provider=tesseract` via `services/documents.ocr_pdf` | Optional extra; disabled by default |
| Storage / Email | `infra/storage.py`, `infra/email.py` | Not AI, same pattern |

### Anthropic adapter

- Official `anthropic` Python SDK; default model `claude-opus-5-5`, configurable.
- Structured outputs via `output_config.format = {type: "json_schema", schema}`. The schema is derived from the
  Pydantic model with `strict_json_schema()` (all properties required, `additionalProperties: false`,
  bounds removed). Pydantic re-validates the result, including the bounds.
- `output_config.effort` from `LLM_EFFORT` (default `medium`).
- Server-side refusal fallback enabled by default (`LLM_FALLBACKS=default`, beta
  `server-side-fallback-2026-07-01`); set `off` to disable.
- `stop_reason == "refusal"` raises `AIError("refusal")`; `max_tokens` raises `AIError("truncated")`.
- SDK exceptions are normalized to `timeout`, `rate_limited`, `unavailable`, `provider_error`, `not_configured`.

**Not verified against the live API in this repository.** No API key was used during development. Real-provider
tests are marked `real_provider` and are opt-in. Run a manual smoke test before relying on it (see TESTING.md).

### Mock provider

`MockLLMProvider` (model `mock-deterministic-v1`) returns deterministic heuristic/template output. The UI labels
its output as development mock output, and configuration validation refuses it in staging/production unless
`ALLOW_MOCK_AI_IN_PRODUCTION=true`.

## Guarded invocation (`careerpilot/ai/client.py`)

`run_structured(db, request, Schema)`:

- bounded concurrency (`LLM_MAX_CONCURRENCY` semaphore)
- circuit breaker (5 consecutive availability failures open it for 60 s)
- at most 2 attempts, retrying only invalid output or transient errors (refusals are never retried)
- JSON extraction + Pydantic validation
- an `ai_usage_records` row per attempt: provider, model, operation, prompt version, tokens, estimated cost,
  latency, success, error code. **Prompts and outputs are never logged.**

## Versioned schemas and prompts

| Task | Schema | Prompt version |
| --- | --- | --- |
| Resume extraction | `ResumeExtraction` (`resume.v1`) | `resume-extract-2026-11-v1` |
| Job requirement extraction | `JobExtraction` (`job.v1`) | `job-extract-2026-11-v1` |
| Cover letter | `CoverLetterOutput` (`cover_letter.v1`) | `cover-letter-2026-11-v1` |

Each extracted fact keeps: value, `source_text`, `source_section`, `confidence`, `method`
(`llm`/`heuristic`), `status` (`stated`/`inferred`/`user_confirmed`/`rejected`), `schema_version`, timestamp.

### Grounding after extraction (`services/resumes._ground`)

- Skills claimed as `stated` that do not appear in the source text are downgraded to `inferred` with confidence ≤ 0.4.
- Skill names are normalized against the taxonomy and de-duplicated.
- Experiences with end before start lose their dates (with a warning); future start dates are dropped.
- Text beyond `LLM_MAX_INPUT_CHARS` is not silently dropped: a warning is added to the extraction.

## Matching (`services/matching.py`, algorithm `rules-v1`)

| Stage | Implementation |
| --- | --- |
| A. Eligibility | Only explicit hard conflicts make a job `ineligible` (currently: onsite/hybrid in another country when the candidate said they will not relocate). Missing data gives `potentially_eligible` or `insufficient_information`, never a failure. |
| B. Representations | Confirmed skills (normalized), confirmed roles, preferences; versioned embeddings in `embeddings` keyed by `(owner_type, owner_id, model)` with a content hash. |
| C. Retrieval | Union of (1) SQL: published, unexpired jobs from non-suspended companies sharing a confirmed skill, (2) pgvector cosine-distance top-N, (3) recent jobs for cold start. Excludes applied/dismissed jobs. |
| D. Ranking | Weighted components, renormalized over components with data. |
| E. Explanation | Matched/missing required and preferred skills, experience sentence, preference conflicts, data coverage, disclaimer. |
| F. Feedback | `recommendation_events` (impression/click/save/apply/interview/offer/hire), recorded only with `recommendation_tracking` consent (dismissals always, as a product action). Never used for automatic retraining. |

Initial, uncalibrated weights:

| Component | Weight |
| --- | --- |
| required_skills | 0.30 |
| preferred_skills | 0.10 |
| experience | 0.15 |
| semantic | 0.15 |
| title | 0.10 |
| location | 0.10 |
| salary | 0.05 |
| employment_type | 0.05 |

The score (0-100) is a **relevance ordering signal, not a probability of hire**, and it is labeled that way in
the UI and API. Protected characteristics are not collected and never used.

The default embedder is a local feature-hashing model (`hashing-v1-512`). It is deterministic and cheap but only
captures lexical overlap. Swap in a real embedding model via `EMBEDDING_PROVIDER=openai_compatible`; vectors are
versioned by model name, so a new model creates new rows.

## Cover letters (`services/generation.py`)

- Requires `ai_processing` consent and some confirmed skills or experience.
- Input is limited to `candidate_facts()` (confirmed data only) and the public job context.
- `find_unsupported_claims()` flags skills not in the confirmed profile, numbers/percentages/years absent from
  the facts, and organizations not in the candidate's history. Flags are recomputed for every saved version and
  stored with submitted documents.
- Drafts are versioned (`cover_letter_drafts`). Submission requires explicit confirmation.

## Fallback when AI is unavailable

| Feature | Behavior |
| --- | --- |
| Resume extraction | Heuristic extraction, with a visible note |
| Job requirement suggestions | 503 `ai_unavailable`; recruiter enters requirements manually |
| Cover letters | 503 `ai_unavailable`; the candidate can write one manually |
| Job search, recommendations | Unaffected (no LLM in the path) |
