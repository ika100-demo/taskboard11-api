# Design — 002 Store tasks in Postgres so they survive restarts

## Decisions

- **Postgres through psycopg 3 (`psycopg[binary]`), sync, one short-lived connection per request.** The handlers are already sync (thread pool). A connection per request means there is no pool state to go stale: a request or readiness check after an outage simply connects again, so `/ready` turns 200 on the first check after the database is back (AC-002.4, AC-002.5), with no pool backoff to tune. A pool is an optimisation for a later spec if latency asks for it. This decision outlives the feature: ADR to create with `cplat adr add postgres-task-storage --decision "Tasks are stored in Postgres via psycopg 3 with one connection per request; the service creates its schema itself at startup with idempotent DDL"`.
- **The service owns its schema with idempotent DDL** (`CREATE TABLE IF NOT EXISTS` under a transaction-scoped advisory lock), run at startup and, when the database was down then, lazily on the first successful connection (AC-002.2, AC-002.5). No Alembic: one table, additive only. The first non-additive change introduces a migration tool (same ADR).
- **Creation order is a `bigint GENERATED ALWAYS AS IDENTITY` column `seq`**, `GET /tasks` orders by it, never by `id` (AC-002.1, notes for this repo).
- **Ids stay `str(uuid.uuid4())`** generated in Python (same format as spec 001), stored in a `uuid` column.
- **Config:** `DATABASE_URL` only (libpq URI; `PG*` are ignored). It is read from the environment **on every connect**, not once at import, so the import-time app object, the lifespan and tests that change the variable all see the current value. Unset or empty `DATABASE_URL` behaves like an unreachable database (503 / not ready), it does not crash the process. The URL is never logged.
- **Timeouts per connection** (spec, Timeouts): `connect_timeout=3`, `options="-c statement_timeout=3000"`, `tcp_user_timeout=3000` (Linux; makes a hung network fail instead of blocking). A task endpoint therefore answers 503 within 5 s whether the database is down or hangs (AC-002.3).
- **Error mapping:** `psycopg.OperationalError` and `psycopg.InterfaceError` (connection refused, timeout, statement timeout, server gone) and a missing `DATABASE_URL` become `DatabaseUnavailableError` in `db.py`; the router turns it into `503 {"detail": "database unavailable"}`. Other `psycopg.Error`s are bugs and stay 500. `/ready` returns 503 on **any** `psycopg.Error` or `DatabaseUnavailableError` (a database that answers but where the schema cannot be created is not ready).
- **No in-memory fallback:** nothing is cached between requests; a failed `POST` runs in one transaction that is never committed, so the task never appears later (AC-002.4, AC-002.5).
- **Titles Postgres cannot store** (containing U+0000 or a lone surrogate, which JSON allows) are rejected with the standard 422 on `title` instead of a 500. This is the only addition to the 001 validation and is not reachable with ordinary text.
- **Single replica no longer required:** state is in the database, so several replicas see the same list. No gitops change: `DATABASE_URL` is wired by the system plan (spec, Provided by the system) and the probe paths are unchanged.

## Modules

| Module | Responsibility | New / changed |
|---|---|---|
| `db.py` | `Database` (connect with timeouts, schema bootstrap, readiness check), `DatabaseUnavailableError` | new |
| `tasks/store.py` | `TaskStore(database)`: `add`, `list` on the `tasks` table | changed (replaces the in-memory store) |
| `tasks/models.py` | `TaskCreate` title also rejects U+0000 / lone surrogates | changed |
| `tasks/api.py` | maps `DatabaseUnavailableError` to 503 | changed |
| `main.py` | lifespan builds `Database` + `TaskStore`, best-effort `ensure_schema`; `/ready` checks the database | changed |
| `tests/conftest.py` | throwaway Postgres cluster and fixtures (below) | changed |
| `devbox.json` | adds the `postgresql` package (test server binaries) | changed |

### Interfaces

```python
# src/taskboard11_api/db.py
class DatabaseUnavailableError(Exception): ...

class Database:
    def __init__(self, url: str | None = None) -> None: ...
        # url None -> os.environ.get("DATABASE_URL") read at each connect
    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection[Any]]:
        # connect (timeouts above); ensure_schema once per URL; yield;
        # commit on success, rollback on exception, always close.
        # OperationalError / InterfaceError / missing URL -> DatabaseUnavailableError (logged once:
        # event "database_unavailable", field error_type=<class name>, never the URL)
    def ensure_schema(self) -> None:   # idempotent; raises DatabaseUnavailableError
    def is_ready(self) -> bool:        # connection() + "SELECT 1"; never raises

# src/taskboard11_api/tasks/store.py
class TaskStore:
    def __init__(self, database: Database) -> None: ...
    def add(self, title: str, due_date: datetime.date | None) -> Task: ...   # raises DatabaseUnavailableError
    def list(self) -> list[Task]: ...                                         # ORDER BY seq; raises DatabaseUnavailableError
```

The "schema ready" memo is a set of URLs guarded by a `threading.Lock`, so a test that points `DATABASE_URL` at a fresh database gets its schema created there too.

## Contract

Unchanged from spec 001 ([../001-create-and-list-tasks-in-memory/design.md](../001-create-and-list-tasks-in-memory/design.md)) for 201, 200 and 422; this spec adds:

| Endpoint | Condition | Status | Body |
|---|---|---|---|
| `POST /tasks` | database unreachable, hangs, or `DATABASE_URL` unset | 503 | `{"detail": "database unavailable"}`; nothing stored, ever (AC-002.3, AC-002.4) |
| `GET /tasks` | same | 503 | `{"detail": "database unavailable"}`, never `[]` from memory (AC-002.3, AC-002.5) |
| `GET /health` | always while the process runs, database irrelevant | 200 | `{"status": "ok"}` |
| `GET /ready` | connect + schema + `SELECT 1` succeed | 200 | `{"status": "ready"}` |
| `GET /ready` | otherwise | 503 | `{"status": "unavailable"}` |

All bounded to 5 s by the timeouts above. A 422 is decided before the database is touched, so an invalid body is 422 even during an outage. `GET /tasks` returns tasks ordered by `seq` (creation order), identical `id`, `title`, `due_date` across restarts (AC-002.1).

**Restart** (AC-002.1, AC-002.2): in-process tests restart the service by leaving and re-entering `with TestClient(app):` (lifespan builds a new `Database`/`TaskStore`; nothing survives in memory). Testers may also start `uvicorn taskboard11_api.main:app` as a subprocess against `pg_server.url`. Spec 001's `test_restart_empties_the_list` (AC-001.7) is superseded by AC-002.1 and is removed by the testers.

## Data

```sql
CREATE TABLE IF NOT EXISTS tasks (
    seq        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id         uuid        NOT NULL UNIQUE,
    title      text        NOT NULL,
    due_date   date        NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Run inside one transaction after `SELECT pg_advisory_xact_lock(2002)` so concurrent replicas starting together do not race on `CREATE TABLE`. Insert: `INSERT INTO tasks (id, title, due_date) VALUES (%s, %s, %s)`. List: `SELECT id, title, due_date FROM tasks ORDER BY seq`; `id` is returned as `str(uuid)`.

## Test harness (tests run against a real Postgres)

`devbox.json` adds `postgresql@16` (provides `initdb`, `pg_ctl`; works in CI through the devbox install action, no Docker). `tests/conftest.py` (written by plan task t1; testers use these fixtures and do not redefine them):

| Fixture | Scope | What |
|---|---|---|
| `pg_server` | session | `initdb -A trust -U postgres` in a tmp dir, `pg_ctl start -w` on `127.0.0.1:<free port>` (`listen_addresses=127.0.0.1`, `unix_socket_directories=''`). Exposes `.url` (database `taskboard_test`), `.stop()` (`pg_ctl stop -m fast -w`), `.start()`, `.ensure_running()`, `.create_database() -> str` (URL of a new, empty, uniquely named database). Clear error if `initdb` is not on `PATH` ("run inside devbox"). Stopped at session end. |
| `_database_env` | session, autouse | sets `DATABASE_URL=pg_server.url` for the whole session (before any test uses the app). |
| `clean_tasks` | function, autouse | `pg_server.ensure_running()`, then `TRUNCATE tasks RESTART IDENTITY` if the table exists, so each test starts with an empty list. |
| `unreachable_database_url` | function | URL to `127.0.0.1` on a port where nothing listens (connection refused). |
| `hanging_database_url` | function | URL to a local socket that accepts and never answers (checks the 5 s bound). |
| `client` | function | unchanged (`TestClient(app)`). |

Outage tests set `monkeypatch.setenv("DATABASE_URL", unreachable_database_url)` or call `pg_server.stop()`; recovery tests call `pg_server.start()` and poll `/ready` for up to 10 s (AC-002.4).

## Observability

`database_unavailable` (warning, `error_type`) once per failed connection or query; `database_unavailable_at_startup` (warning) when the lifespan cannot create the schema; `schema_ready` (info) once per URL. No title, no URL in logs. Existing request metrics show the 503s; no new metrics.
