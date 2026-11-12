# Architecture decision records

| ADR | Decision |
|---|---|
| [001](001-postgres-task-storage.md) | Tasks are stored in Postgres via psycopg 3 with one connection per request; the service creates its schema itself at startup with idempotent DDL |
