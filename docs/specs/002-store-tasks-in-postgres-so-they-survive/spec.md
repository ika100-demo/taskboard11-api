---
spec_id: 002-store-tasks-in-postgres-so-they-survive
title: Store tasks in Postgres so they survive restarts, and answer 503 while the database is unreachable
status: done
priority: P1
shape: service-python
parent: ika100-demo/taskboard11-gitops:001-persistent-tasks-with-web-ui
---

# 002 — Store tasks in Postgres so they survive restarts, and answer 503 while the database is unreachable

## Problem

The Task API keeps tasks in memory, so every restart or redeploy of the API loses every task, and the API is the only way to see or record one. People who are not API clients cannot use the taskboard at all, and the web component shows only a starter page. Storing tasks in a Postgres database makes them survive restarts, and a task page in the web UI lets people list and create tasks without calling the API by hand.

## System context

Slice of the system plan `001-persistent-tasks-with-web-ui` in `ika100-demo/taskboard11-gitops` for `taskboard11-api` (service-python). The system criteria and the contract below are binding: every criterion of this spec implements one of them and names it: `(system AC-<NNN>.<n>)`.

### System criteria

- **AC-001.1** Given tasks were created through `POST /tasks`, when the Task API restarts or is redeployed, then `GET /tasks` returns 200 with each of those tasks, with the same `id`, `title` and `due_date`, in creation order.
- **AC-001.2** Given the database cannot be reached, when a client sends `POST /tasks` or `GET /tasks`, then the response is 503, the Task API's readiness check fails, and once the database is back a task sent during the outage is not in `GET /tasks`.

### Contract

The Task API keeps the format of its spec `001-create-and-list-tasks-in-memory` unchanged; this spec adds only 503 and the readiness behaviour. Base URL for the web UI: `TASK_API_URL` (dev: `http://taskboard11-api`), called from the web server only. JSON, UTF-8, `Content-Type: application/json`.

**Task object**

| Field | Type | Notes |
|---|---|---|
| `id` | string | server-assigned, opaque, non-empty; never sent by the client (ignored if sent) |
| `title` | string | 1 to 200 characters, at least one non-whitespace character, stored and returned exactly as sent |
| `due_date` | string or null | calendar date `YYYY-MM-DD`; past dates allowed; `null` when there is none |

**`POST /tasks`** — create a task. Request body `{"title": "<title>", "due_date": "YYYY-MM-DD" | null}` (`due_date` may be omitted, which equals `null`).

| Status | Body | Meaning |
|---|---|---|
| 201 | the Task object | created and stored in the database |
| 422 | FastAPI validation body `{"detail": [...]}` | title or due date invalid; nothing created |
| 503 | `{"detail": "database unavailable"}` | database unreachable; nothing created, the task never appears later |

**`GET /tasks`** — list all tasks, oldest first (creation order), no paging.

| Status | Body | Meaning |
|---|---|---|
| 200 | JSON array of Task objects (`[]` when none) | |
| 503 | `{"detail": "database unavailable"}` | database unreachable |

**Probes** (platform, not the web UI): `GET /health` 200 `{"status": "ok"}` while the process runs, independent of the database; `GET /ready` 200 `{"status": "ready"}` when the database answers, else 503 `{"status": "unavailable"}`.

**Web UI to user** (inside the web repo, listed for completeness): the task page is `/`; texts exactly "No tasks yet", "No due date", "Title must be 1 to 200 characters", "Tasks could not be loaded. Try again later.", "Task could not be saved. Try again."

### Errors

- Error bodies of the Task API are JSON with a `detail` field: a string for 503, the FastAPI validation list for 422. The web UI never shows `detail` to the user; it maps outcomes to its fixed texts.
- The web UI treats any response the contract does not list for a call (other 4xx, 5xx, a 200 to `POST`, a 201 to `GET`, a body that is not the expected JSON shape), a connection error and a timeout the same as 503: on `GET /tasks` it shows "Tasks could not be loaded. Try again later."; on `POST /tasks` it shows "Task could not be saved. Try again." and keeps the entered values. A 422 on `POST` (which the client-side check should prevent) is also shown as "Task could not be saved. Try again."
- The web UI logs each failed call once (`@/lib/logger`, with status or error kind, never the task title), and does not retry automatically.

### Timeouts

- Web server to Task API, `GET /tasks` and `POST /tasks`: 5 seconds total per call; on expiry the call is aborted and handled as an error above. No retries.
- Task API to Postgres: connect timeout 3 seconds, statement timeout 3 seconds, so a task endpoint answers 503 within 5 seconds when the database is down or hangs; the readiness check uses the same bound and answers within 5 seconds.
- Database down at API start: the API starts anyway (liveness 200, readiness 503) and reconnects on the next request or readiness check; once the database is back `/ready` turns 200 within 10 seconds without a restart.
- Task API down or not ready: Kubernetes removes it from the Service, so the web UI gets a connection error or timeout and shows its error texts; the web UI's own readiness does not depend on the Task API.

### Provided by the system

The gitops part of this plan wires these for this repo; rely on them, do not ask for them again:

- resource `postgres`: env `DATABASE_URL`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`

### Notes for this repo

Persistence replaces the in-memory TaskStore; the request/response format of POST/GET /tasks stays exactly as
in spec 001 (AC-001.1 to AC-001.6 of that spec stay active). Only AC-001.7 of spec 001 is superseded.
Connection comes from DATABASE_URL (PG* also set by the platform). Creation order must be stable across
restarts: order by a monotonically increasing column (e.g. a bigserial or created_at plus sequence), never by id.
Tests run against a real Postgres (the repo's devbox / a test container), not a mock.

## Stories

<!-- As a <persona>, I want <goal>, so that <benefit>. -->

## Acceptance criteria

- **AC-002.1** Given tasks were created through `POST /tasks` against the database in `DATABASE_URL`, when the service process is restarted against the same database, then `GET /tasks` returns 200 with each of those tasks, with the same `id`, `title` and `due_date`, in creation order (system AC-001.1) (replaces AC-001.7)
- **AC-002.2** Given `DATABASE_URL` points to an empty database, when the service starts, then it creates its own schema and `POST /tasks` then `GET /tasks` work, and a second start against the same database keeps the existing tasks (system AC-001.1)
- **AC-002.3** Given the database is unreachable, when a client sends `POST /tasks` or `GET /tasks`, then the response is 503 with the body `{"detail": "database unavailable"}` within 5 seconds, `GET /ready` returns 503 and `GET /health` stays 200 (system AC-001.2)
- **AC-002.4** Given a `POST /tasks` was answered 503 while the database was unreachable, when the database is reachable again, then `GET /ready` returns 200 within 10 seconds without a restart of the service, and `GET /tasks` does not contain the task sent during the outage (system AC-001.2)
- **AC-002.5** Given the database is unreachable when the service starts, when a client calls `GET /health` and `GET /ready`, then the process is running, `/health` returns 200 and `/ready` returns 503, and the task endpoints answer 503, never an empty list from memory (system AC-001.2)

## Non-goals

## Assumptions

<!-- Spec 149: decisions taken by default, approved with the spec. One bullet each: - **A1** <the decision> (other option: <…>; affects AC-…). A revised one is struck through (~~…~~), never deleted. -->

## Open questions

<!-- Only what may not be decided by default (spec 149): security or access, money, destroying or migrating data, or a request too ambiguous to build. Approval is refused while any is open. Strike answered ones (~~…~~) and fold the answer into the criteria. -->

## Changelog

- 2026-11-12 created from the system plan, with its criteria (spec 147)
- 2026-11-12 approved
- 2026-11-12 building
- 2026-11-12 done
