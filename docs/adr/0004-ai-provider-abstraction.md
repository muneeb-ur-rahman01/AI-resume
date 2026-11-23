# ADR 0004: Provider-independent AI with deterministic guards

- Status: Accepted (2026-11-17)

## Decision

- `LLMProvider` / `EmbeddingProvider` protocols, selected by configuration. First implementations: Anthropic
  (official SDK, `claude-opus-5-5` default, structured JSON-schema outputs, refusal fallback) and a clearly labeled
  deterministic mock used in tests and local development.
- A local feature-hashing embedder is the default so the system works with no external calls. An
  OpenAI-compatible HTTP embedder covers hosted embedding APIs.
- All model output is validated against versioned Pydantic schemas, grounded against source text, and used only as
  suggestions. Ranking, eligibility and explanations are deterministic code (`rules-v1`).
- A reranker is not used until offline evaluation shows a benefit (AI_EVALUATION.md).

## Consequences

Provider swaps are configuration changes. Costs and failures are visible in `ai_usage_records`. Quality depends on
future evaluation work; the hashing embedder is a weak semantic signal until replaced.
