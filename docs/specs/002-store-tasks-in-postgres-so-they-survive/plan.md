---
spec_id: 002-store-tasks-in-postgres-so-they-survive
shape: service-python
spec_hash: 5dc1654e02f0
summary: Postgres-backed TaskStore (psycopg 3), self-created schema, 503 and failing readiness while the database is unreachable
tasks:
  - id: t1
    title: Add the Database module, psycopg dependency and the real-Postgres test harness
    files: [src/taskboard11_api/db.py, pyproject.toml, uv.lock, devbox.json, tests/conftest.py, tests/test_db.py]
    covers: [AC-002.2, AC-002.3, AC-002.4, AC-002.5]
    parallel_safe: true
    depends_on: []
    done: true
  - id: t3
    title: Postgres-backed TaskStore wired into the lifespan, outages mapped to 503 and /ready checking the database
    files: [src/taskboard11_api/tasks/store.py, src/taskboard11_api/tasks/models.py, tests/test_task_store.py, tests/test_task_models.py, src/taskboard11_api/main.py, src/taskboard11_api/tasks/api.py, tests/test_app_database.py, docs/env-vars.md]
    covers: [AC-002.1, AC-002.2, AC-002.3, AC-002.4, AC-002.5]
    parallel_safe: true
    depends_on: [t1]
    done: true
---

# Plan — 002 Store tasks in Postgres so they survive restarts

Contract, interfaces, schema and test fixtures: [design.md](design.md).

## t1 — Add the Database module, psycopg dependency and the real-Postgres test harness

**Files:** src/taskboard11_api/db.py, pyproject.toml, uv.lock, devbox.json, tests/conftest.py, tests/test_db.py
**Covers:** AC-002.2, AC-002.3, AC-002.4, AC-002.5
**Goal:** A `Database` that connects with the spec's timeouts, creates the schema idempotently, reports readiness and turns every outage into `DatabaseUnavailableError`; plus the throwaway Postgres cluster all tests of this spec run against.

**Implementation notes:**
- `pyproject.toml`: add `psycopg[binary]>=3.2` to `dependencies`; regenerate `uv.lock` inside devbox (`uv lock`), never `pip`/`uv add`. `devbox.json`: add the package `postgresql@16` only, leave the template recipes untouched.
- `db.py` per design "Interfaces": `Database(url: str | None = None)`; the URL is `url or os.environ.get("DATABASE_URL")`, read at each connect; empty or unset raises `DatabaseUnavailableError`.
- `psycopg.connect(conninfo, connect_timeout=3, options="-c statement_timeout=3000", tcp_user_timeout=3000)`.
- `connection()` context manager: connect, `ensure_schema` once per URL (memo set + `threading.Lock`), yield, commit / rollback, always close; map `OperationalError`, `InterfaceError` to `DatabaseUnavailableError` (chained), log `database_unavailable` with `error_type` only.
- `ensure_schema()`: one transaction, `SELECT pg_advisory_xact_lock(2002)` then the `CREATE TABLE IF NOT EXISTS tasks` of design "Data"; log `schema_ready` once per URL.
- `is_ready() -> bool`: `connection()` + `SELECT 1`; `False` on any `psycopg.Error` or `DatabaseUnavailableError`; never raises.
- `tests/conftest.py`: keep the `client` fixture; add `pg_server`, `_database_env`, `clean_tasks`, `unreachable_database_url`, `hanging_database_url` exactly as in design "Test harness" (TCP on 127.0.0.1, no unix socket, clear error when `initdb` is missing).
- `tests/test_db.py`: unit tests for schema creation on an empty database (twice, idempotent), `is_ready` true/false (unreachable, hanging within 5 s, unset URL), recovery after `pg_server.stop()`/`start()` with the same `Database` object.
- mypy strict clean; bandit clean (no string-built SQL).

**Done when:** `tests/test_db.py` passes against the fixture cluster and the existing suite still passes with the new autouse fixtures (`devbox run test`), `devbox run quality` is green. Acceptance tests pass only after t3.

## t3 — Postgres-backed TaskStore wired into the lifespan, outages mapped to 503 and /ready checking the database

Merges the former t2 (Postgres-backed `TaskStore`): `tests/conftest.py` imports `main.py`, so the store cannot be verified before `main.py` is wired (decision of the user, 2026-11-12).

**Files:** src/taskboard11_api/tasks/store.py, src/taskboard11_api/tasks/models.py, tests/test_task_store.py, tests/test_task_models.py, src/taskboard11_api/main.py, src/taskboard11_api/tasks/api.py, tests/test_app_database.py, docs/env-vars.md
**Covers:** AC-002.1, AC-002.2, AC-002.3, AC-002.4, AC-002.5
**Goal:** `TaskStore(database)` stores and lists tasks in the `tasks` table in creation order, with the same task format as spec 001; and the endpoints of the contract: tasks persisted across restarts, 503 `{"detail": "database unavailable"}` during outages, `/health` independent of the database, `/ready` 200/503 by the database.

**Implementation notes:**
- `TaskStore.__init__(self, database: Database)`; no lock, no list, nothing kept in memory.
- `add`: `id = str(uuid.uuid4())`, parameterised `INSERT INTO tasks (id, title, due_date)` inside `database.connection()`; return `Task(id, title, due_date)`.
- `list`: `SELECT id, title, due_date FROM tasks ORDER BY seq`; `id` as `str(uuid)`.
- `DatabaseUnavailableError` propagates unchanged; no FastAPI imports.
- `models.py`: the `title` validator also rejects `"\x00"` and strings that do not encode as UTF-8 (lone surrogates) with a `ValueError` (design "Decisions"); everything else unchanged.
- `tests/test_task_store.py`: rewrite for the Postgres store (order across a new `TaskStore`/`Database` on the same URL, distinct uuid ids, concurrent adds from threads, `DatabaseUnavailableError` on an unreachable URL). Drop the in-memory and lifespan tests (lifespan tests move to `tests/test_app_database.py`).
- `tests/test_task_models.py`: add the U+0000 and lone-surrogate cases.
- `main.py` import time: `app.state.database = Database()`, `app.state.task_store = TaskStore(app.state.database)` (no database call at import).
- Lifespan startup: build a new `Database()` and `TaskStore`, then `ensure_schema()` in `try/except DatabaseUnavailableError` logging `database_unavailable_at_startup`; never fail startup (AC-002.5).
- `/ready`: `request.app.state.database.is_ready()` → 200 `{"status": "ready"}`, else `JSONResponse(503, {"status": "unavailable"})`. `/health`, `/ping`, `/metrics` unchanged.
- `api.py`: wrap `store.add` / `store.list` in `except DatabaseUnavailableError` → `HTTPException(status_code=503, detail="database unavailable")`; keep `task_created` logging; validation stays before the store call (422 during an outage).
- `tests/test_app_database.py`: `get_task_store` returns `app.state.task_store`; each lifespan startup installs a new store on the same database (no in-memory state); startup with an unreachable URL succeeds.
- `docs/env-vars.md`: add a "Database" section with `DATABASE_URL` (required, libpq URI, set by the system's `postgres` resource; unset means not ready) and the fixed timeouts.

**Done when:** `tests/test_task_store.py` and `tests/test_task_models.py` pass, all acceptance tests for AC-002.1 to AC-002.5 and spec 001's AC-001.1 to AC-001.6 pass, the existing `test_health.py` passes unchanged, and `devbox run ci` is green.
