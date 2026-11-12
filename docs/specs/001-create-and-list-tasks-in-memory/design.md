# Design — 001 Create and list tasks in memory

## Decisions

- **A new `tasks` package** (`src/taskboard11_api/tasks/`) holds the model, the store and the router; `main.py` only includes the router. This keeps `main.py` to wiring and gives the next storage spec one module (`store.py`) to replace.
- **Storage is an in-process `TaskStore`** (a list in insertion order guarded by a `threading.Lock`): FastAPI runs the sync handlers in a thread pool, so concurrent creates must not interleave. It is feature-local and explicitly temporary (the spec defers the storage decision), so no ADR.
- **The store lives on `app.state.task_store`** and is replaced with a fresh `TaskStore()` in the app's lifespan startup. A process start (and, in tests, each `with TestClient(app):` block) therefore begins with an empty list (AC-001.7). It is also created once at import time, so a `TestClient(app)` used without `with` (as in `tests/conftest.py`) still works. Handlers get it through the dependency `get_task_store(request) -> TaskStore`.
- **`due_date` is validated by hand, not by pydantic's lax `date` parsing**: lax mode also accepts date-times with a zero time and Unix timestamps, which A2 rejects. A `mode="before"` validator requires `None` or a `str` matching `^\d{4}-\d{2}-\d{2}$`, then `datetime.date.fromisoformat` (rejects `2026-02-30`) (AC-001.5).
- **Ids are `str(uuid.uuid4())`** (A7). Unknown body fields, including `id`, are ignored (pydantic's default `extra="ignore"`).
- **Validation errors use FastAPI's standard 422 body** (A5); no custom exception handler.
- **Single replica:** tasks are per process (non-goal: sharing between instances). No change to the gitops entry is required; with more than one replica, clients would see different lists. The entry's replica count stays as is (1 by default).

## Modules

| Module | Responsibility | New / changed |
|---|---|---|
| `tasks/__init__.py` | re-exports `router` | new |
| `tasks/models.py` | `TaskCreate` (request, validation), `Task` (response) | new |
| `tasks/store.py` | `TaskStore`: `add(title, due_date) -> Task`, `list() -> list[Task]` | new |
| `tasks/api.py` | `APIRouter` with `POST /tasks`, `GET /tasks`; `get_task_store` dependency | new |
| `main.py` | lifespan creating the store; `app.include_router(tasks.router)` | changed |

## Contract

### `POST /tasks`

Request body (`application/json`), object:

| Field | Type | Rules |
|---|---|---|
| `title` | string, required | 1 to 200 characters (Python `len`), at least one non-whitespace character; stored and returned exactly as sent, no trimming (A4). Non-string values (number, null, object) are rejected. |
| `due_date` | string or null, optional | Absent or `null` → stored as `null` (AC-001.2). Otherwise exactly `YYYY-MM-DD` and a real calendar date; past dates accepted (A3). A date-time, `"tomorrow"`, `"2026-02-30"`, `"2026-1-5"` or a number → 422 (AC-001.5). |
| anything else | — | ignored, including a client-supplied `id` (A7). |

Responses:

- `201 Created`, `application/json`:
  ```json
  {"id": "3f1c…-uuid4", "title": "Buy milk", "due_date": "2026-12-01"}
  ```
  Exactly these three keys. `id` is a non-empty string, unique per process (AC-001.1, AC-001.6). `due_date` is the `YYYY-MM-DD` string or `null` (AC-001.2).
- `422 Unprocessable Entity`, FastAPI standard body, no task stored (AC-001.4, AC-001.5):
  ```json
  {"detail": [{"type": "...", "loc": ["body", "title"], "msg": "...", "input": "..."}]}
  ```
  Also returned for a missing body, malformed JSON, or a body that is not a JSON object. Tests assert the status and that `detail` is a non-empty list; `loc`'s last element names the offending field (`title` or `due_date`).

### `GET /tasks`

- `200 OK`, `application/json`: array of task objects (same shape as the 201 body), all tasks, oldest first (creation order), no pagination (AC-001.3, A6). Empty store → `[]` (AC-001.7).

### Restart semantics (AC-001.7)

Tasks exist only in the process. In-process tests simulate a restart by opening a new `with TestClient(app) as client:` block (lifespan startup installs a new empty `TaskStore`). Tasks created through a client that was not entered with `with` live in the import-time store and persist across tests in one pytest session, so tests that count tasks compare before/after or use a `with` block.

## Data

```python
class TaskCreate(BaseModel):          # request
    title: str                        # validator: 1..200 chars, not only whitespace (strict str)
    due_date: datetime.date | None = None   # before-validator: None or ^\d{4}-\d{2}-\d{2}$ + fromisoformat

class Task(BaseModel):                # response and stored item
    id: str
    title: str
    due_date: datetime.date | None    # serialized as "YYYY-MM-DD" or null
```

`title` uses `Field(min_length=1, max_length=200)` with `strict=True` plus an `after` validator `if not v.strip(): raise ValueError("title must not be blank")`.

## Observability

`POST /tasks` logs `task_created` with `task_id` via structlog (never the title, which is user content). Existing metrics middleware covers request counts and latency; no new metrics.
