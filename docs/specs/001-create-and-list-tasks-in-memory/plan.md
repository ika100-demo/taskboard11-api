---
spec_id: 001-create-and-list-tasks-in-memory
shape: service-python
spec_hash: d19a02a63aaa
summary: In-memory task model, store and POST/GET /tasks endpoints
tasks:
  - id: t1
    title: Add Task models and thread-safe in-memory TaskStore
    files: [src/taskboard11_api/tasks/models.py, src/taskboard11_api/tasks/store.py]
    covers: [AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6]
    parallel_safe: true
    depends_on: []
  - id: t2
    title: Expose POST/GET /tasks and wire the store into the app lifespan
    files: [src/taskboard11_api/tasks/__init__.py, src/taskboard11_api/tasks/api.py, src/taskboard11_api/main.py]
    covers: [AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7]
    parallel_safe: true
    depends_on: [t1]
---

# Plan — 001 Create and list tasks in memory

Contract and decisions: [design.md](design.md).

## t1 — Add Task models and thread-safe in-memory TaskStore

**Files:** src/taskboard11_api/tasks/models.py, src/taskboard11_api/tasks/store.py
**Covers:** AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6
**Goal:** The request/response models with all validation rules of the contract, and a store that keeps tasks in creation order with unique ids.

**Implementation notes:**
- `TaskCreate`: `title: str = Field(min_length=1, max_length=200, strict=True)` plus an `after` validator rejecting whitespace-only titles; no trimming (A4).
- `TaskCreate.due_date: datetime.date | None = None` with a `mode="before"` validator: `None` passes; otherwise must be a `str` matching `^\d{4}-\d{2}-\d{2}$`, then `datetime.date.fromisoformat` (a `ValueError` becomes a 422). Rejects date-times, numbers, `2026-02-30`.
- Leave `extra` at the default (ignore), so a client `id` and unknown fields are dropped (A7).
- `Task(id: str, title: str, due_date: date | None)`; serializes `due_date` as `YYYY-MM-DD` or `null`.
- `TaskStore`: `add(title: str, due_date: date | None) -> Task` assigns `str(uuid.uuid4())` and appends; `list() -> list[Task]` returns a copy in insertion order. Both under a `threading.Lock`.
- No FastAPI imports in this task's files; mypy strict clean.

**Done when:** unit tests for the models (each 422 case of AC-001.4/AC-001.5 raises `ValidationError`; valid inputs pass) and the store (order, distinct ids) pass; `devbox run quality` passes. The HTTP acceptance tests pass only after t2.

## t2 — Expose POST/GET /tasks and wire the store into the app lifespan

**Files:** src/taskboard11_api/tasks/__init__.py, src/taskboard11_api/tasks/api.py, src/taskboard11_api/main.py
**Covers:** AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7
**Goal:** The two endpoints of the contract, backed by a per-process store that starts empty on every app startup.

**Implementation notes:**
- `api.py`: `router = APIRouter()`; `get_task_store(request: Request) -> TaskStore` returns `request.app.state.task_store`.
- `POST /tasks` (`status_code=201`, `response_model=Task`): `store.add(body.title, body.due_date)`; log `task_created` with `task_id` via structlog (no title in logs).
- `GET /tasks` (`response_model=list[Task]`): `store.list()`.
- `tasks/__init__.py` re-exports `router`.
- `main.py`: set `app.state.task_store = TaskStore()` right after creating `app`; add a `lifespan` async context manager that sets a fresh `TaskStore()` on startup (restart = empty list, AC-001.7); `app.include_router(tasks.router)`. Leave `/health`, `/ready`, `/ping`, `/metrics` unchanged.
- Sync handlers (FastAPI runs them in the thread pool; the store's lock covers concurrency).

**Done when:** all acceptance tests for AC-001.1 to AC-001.7 pass, existing tests still pass, and `devbox run ci` is green.
