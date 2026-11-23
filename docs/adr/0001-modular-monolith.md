# ADR 0001: Modular monolith with a separate worker process

- Status: Accepted (2026-11-17)

## Context

The product spans about 20 domain modules but has one team, no traffic yet, and strong consistency needs
(applications, verification, consent). The specification asks for no microservices without demonstrated need.

## Decision

One Python package (`careerpilot`) with layered modules (routers → services → models/infra/ai). The HTTP API
and the Celery worker are separate processes built from the same image. The specification's suggested
top-level `ai/`, `database/` and `services/worker/` folders are folded into the package
(`careerpilot/ai`, `services/api/alembic`, `careerpilot/worker.py`) so Python imports and typing work without
path hacks. Tests live next to the API (`services/api/tests`); browser e2e tests live in `apps/web/e2e`.

## Consequences

Simple deployment and transactions. Module boundaries are enforced by convention and review, not by process
isolation. A module can be extracted later if load or team structure requires it.
