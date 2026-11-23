# ADR 0002: PostgreSQL + pgvector for relational and vector data

- Status: Accepted (2026-11-17)

## Decision

Use PostgreSQL 17 with pgvector for everything, including embeddings. Do not add a separate vector database.
The `embeddings.vector` column is dimension-less so several embedding models can coexist (rows keyed by model
name). ANN indexes (HNSW) are added per model and dimension once data volume justifies them; the initial
retrieval uses exact cosine ordering over pre-filtered published jobs.

Tests may run on SQLite through a `Vector` TypeDecorator (JSON fallback, in-Python cosine). CI also runs the full
suite on PostgreSQL + pgvector, which already caught a column-length bug that SQLite ignores.

## Consequences

One system to operate, back up and secure. Vector search scales to roughly millions of rows with HNSW. Revisit
if the corpus or latency needs exceed that.
