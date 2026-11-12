# Verification — 001 Create and list tasks in memory

**Result:** pass
**Commit:** 15acb7d · **Base:** 103a364 · **Trace:** 7/7 criteria named by tests (smoke: AC-001.1, AC-001.3)

| Criterion | Verdict | Tests | Implementation | Notes |
|---|---|---|---|---|
| AC-001.1 | met | `tests/test_tasks.py::test_create_task_returns_201_with_fields`; smoke `tests/test_smoke_tasks.py::test_ac_001_1_create_task_at_the_base_url` | `src/taskboard11_api/tasks/api.py:26-31`, `src/taskboard11_api/tasks/store.py:17-22` | asserts 201, exactly the keys `id`/`title`/`due_date`, non-empty string `id`, `"Buy milk"`, `"2026-12-01"`; the smoke test asserts the same at the base URL with a `smoke-<uuid>` title |
| AC-001.2 | met | `tests/test_tasks.py::test_ac_001_2_create_task_without_due_date[payload0,payload1]` | `src/taskboard11_api/tasks/models.py:16,28-29` | covers both a missing `due_date` and `null`; asserts 201 and `due_date is None` |
| AC-001.3 | met | `tests/test_tasks.py::test_list_tasks_in_creation_order`; smoke `tests/test_smoke_tasks.py::test_ac_001_3_created_tasks_are_listed_in_order`, `::test_ac_001_3_list_tasks_is_readable` | `src/taskboard11_api/tasks/api.py:34-37`, `src/taskboard11_api/tasks/store.py:24-27` | on an empty store, the list equals the creation bodies exactly (each once, same fields, order A, B, C); the smoke test checks relative order and that each appears in a shared list |
| AC-001.4 | met | `tests/test_tasks.py::test_ac_001_4_bad_title_is_422_not_stored[...]` (missing, missing with due_date, `""`, `"   "`, 201 chars, null, number), `::test_title_of_200_characters_is_accepted` | `src/taskboard11_api/tasks/models.py:15,18-23` | asserts 422, a non-empty `detail` whose `loc` ends in `title`, and a following `GET /tasks` == `[]`; the 200-character boundary is accepted |
| AC-001.5 | met | `tests/test_tasks.py::test_ac_001_5_bad_due_date_is_422_not_stored[...]` (`tomorrow`, `2026-02-30`, `2026-1-5`, a date-time, a number) | `src/taskboard11_api/tasks/models.py:9,25-32` | asserts 422, `loc` ends in `due_date`, and nothing stored; `2026-02-30` passes the regex and is rejected by `date.fromisoformat` (line 32) |
| AC-001.6 | met | `tests/test_tasks.py::test_same_title_twice_gives_distinct_ids` | `src/taskboard11_api/tasks/store.py:19` (`uuid4`) | both listed, the ids differ, and the listed ids match the created ids |
| AC-001.7 | met | `tests/test_tasks.py::test_restart_empties_the_list` | `src/taskboard11_api/main.py:26-30,33` | creates a task, then a new lifespan startup (second `with TestClient(app)`) gives 200 `[]`, the restart the design's contract describes |

## Non-goals

- No persistence or sharing between instances: the store is a process-local list (`store.py:15`). ✔
- No single-task read, update, complete or delete routes; only `POST /tasks` and `GET /tasks` (`api.py:26,34`). ✔
- No filtering, sorting or pagination parameters on `GET /tasks`. ✔
- No authentication or per-user lists. ✔
- No due times or time zones: date-times are rejected (`models.py:30`). ✔
- Template-owned parts are unchanged: `/health`, `/ready`, `/ping`, `/metrics`, the metrics middleware and tracing setup are as before (diff of `main.py` only adds the lifespan, the store and `include_router`). ✔

## Deviations from the plan

- `tests/test_smoke_tasks.py` and `tests/test_tasks.py` (acceptance tests from the red commit `b72dcea`) and `tests/test_task_models.py` and `tests/test_task_store.py` (unit tests, `15acb7d`) are in no task's `files`. Acceptable: tests are not in tasks' `files` by convention, and t1's "Done when" asks for these unit tests.
- `tests/test_smoke_tasks.py::test_ac_001_1_invalid_task_is_rejected` names AC-001.1 but checks a 422 for an empty title (AC-001.4 behaviour). Acceptable: it is an extra read-only smoke check; AC-001.1's own smoke test asserts the criterion as written.
- Every task is `done: true` (t1, t2).

## Contract

Matches `design.md`: a `tasks` package with `models.py`/`store.py`/`api.py`/`__init__.py`; `TaskStore` is a list guarded by a `threading.Lock` (`store.py:14`); `app.state.task_store` is set at import (`main.py:34`) and replaced on lifespan startup (`main.py:29`); `get_task_store` dependency (`api.py:17-20`); strict `title` with `Field(min_length=1, max_length=200, strict=True)` plus a blank check; `due_date` before-validator with `^\d{4}-\d{2}-\d{2}$` and `fromisoformat`; `uuid4` string ids; `extra` left at its default (ignore); FastAPI's standard 422 body; `task_created` logged with `task_id` only, no title (`api.py:30`). ✔

## Mutation check (report only)

15 of 16 mutants of the changed code were caught by the acceptance tests (94 %; spec 152, report only).

Survived (a test that names the criterion would fail if it checked this):
- `src/taskboard11_api/tasks/models.py:15 True → False`
