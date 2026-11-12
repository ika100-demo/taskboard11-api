# ADR-001: Postgres task storage

**Status:** Proposed (2026-11-12)

## Context

Spec 002 requires tasks to survive restarts. The system plan already provides a `postgres` resource and `DATABASE_URL`; the service has to use it and must stay up (liveness) while the database is down.

## Decision

Tasks are stored in Postgres via psycopg 3 with one connection per request; the service creates its schema itself at startup with idempotent DDL

## Consequences

- Tasks persist across restarts; the service keeps no task state in memory.
- Database outages map to 503 on the task endpoints and to a failing `/ready`; `/health` stays independent of the database.
- Schema creation is guarded by an advisory lock and `CREATE TABLE IF NOT EXISTS`; a later schema change needs a migration approach (for example Alembic) instead of this DDL.
- Tests run against a real throwaway Postgres cluster (`postgresql@16` in devbox), not a mock.
- One connection per request is simple but does not pool; revisit if load requires it.
