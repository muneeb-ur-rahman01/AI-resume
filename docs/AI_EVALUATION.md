# AI evaluation

**Status:** the evaluation framework is designed but only partly implemented. Unit tests check schema
validation, grounding, heuristic extraction, ranking monotonicity and unsupported-claim detection on synthetic
fixtures. **No accuracy, relevance, latency or cost benchmarks have been measured.** No numbers are claimed here.

## What exists

- Deterministic tests: `tests/unit/test_core_units.py` (heuristic extraction on a synthetic resume, skill
  false-positive guards, prompt-injection warning, ranking order, eligibility semantics, claim detection) and
  `tests/unit/test_ai_client.py` (malformed output, bounded retries, refusals, circuit breaker).
- Telemetry for future evaluation: `ai_usage_records` (tokens, estimated cost, latency, errors per operation and
  prompt version), `job_recommendations` (components and algorithm version), consented `recommendation_events`,
  application outcomes in `application_status_history`.

## Planned harness (`services/api/careerpilot/ai/evaluation/`, not yet created)

| Metric | Dataset | Method |
| --- | --- | --- |
| Resume extraction precision/recall per field | 100+ synthetic resumes with gold JSON (varied layouts, PDF + DOCX, scanned) | Field-level exact/fuzzy match; report per method (`llm`, `heuristic`) |
| Skill normalization accuracy | Alias list + noisy variants | Exact canonical match |
| Job extraction accuracy | Synthetic postings with gold required/preferred splits | Set precision/recall |
| Unsupported-claim rate | Generated letters for synthetic profiles | Detector + human audit sample |
| Cover-letter factuality | Same | Human rubric (2 reviewers) |
| Ranking quality | Labeled candidate-job relevance pairs (graded 0-3) | Precision@K, Recall@K, NDCG@10 vs. baselines (skills-only, embeddings-only) |
| OCR quality | Scanned synthetic resumes | Character error rate |
| Latency / cost | Recorded runs | p50/p95 per operation; USD per processed resume and per recommendation request |

Rules:

- Pin model, prompt and schema versions per run; store results under `docs/evaluation-results/` with the commit SHA.
- Treat regressions above an agreed threshold as release blockers once baselines exist.
- Calibrate `matching.WEIGHTS` only from labeled or consented outcome data; never auto-train from unreviewed feedback.
- Do not assume higher embedding similarity means a better match; report it as one component only.

## Fairness

Protected attributes are neither collected nor used. Disparate-impact analysis needs lawful, consented,
governed demographic data and qualified human review; it is out of scope until such a program exists. Proxy risks
(location, school names, employment gaps) should be reviewed before using any learned ranking.
