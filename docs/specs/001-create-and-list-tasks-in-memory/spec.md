---
spec_id: 001-create-and-list-tasks-in-memory
title: Create and list tasks in memory
status: done
priority: P1
shape: service-python
---

# 001 — Create and list tasks in memory

## Problem

The Task API has no tasks yet: it only answers health and readiness checks, so a client has nothing to record work against. The first useful step is to let a client record a task with a title and an optional due date and to read the tasks back. Keeping them in memory gives clients a working API now, before any decision on storage.

## Stories

As an API client, I want to create a task with a title and, if I have one, a due date, so that I can record work to be done.

As an API client, I want to list all tasks, so that I can show what has been recorded.

## Acceptance criteria

- **AC-001.1** Given the service is running, when a client sends `POST /tasks` with `{"title": "Buy milk", "due_date": "2026-12-01"}`, then the response is 201 with a JSON body containing a server-assigned non-empty string `id`, `"title": "Buy milk"` and `"due_date": "2026-12-01"`. (smoke)
- **AC-001.2** Given the service is running, when a client sends `POST /tasks` with `{"title": "Buy milk"}` and no `due_date` (or `"due_date": null`), then the response is 201 and the body contains `"due_date": null`.
- **AC-001.3** Given tasks A, B and C were created in that order, when a client sends `GET /tasks`, then the response is 200 with a JSON array that contains each of the three tasks once, with `id`, `title` and `due_date` as returned on creation, A before B before C. (smoke)
- **AC-001.4** Given the service is running, when a client sends `POST /tasks` with the `title` missing, empty, only whitespace, or longer than 200 characters, then the response is 422, and a following `GET /tasks` does not contain a new task.
- **AC-001.5** Given the service is running, when a client sends `POST /tasks` with a `due_date` that is not a valid calendar date in the form `YYYY-MM-DD` (for example `"tomorrow"` or `"2026-02-30"`), then the response is 422 and no task is created.
- **AC-001.6** Given two tasks were created with the same title, when a client lists tasks, then both appear, with different `id` values.
- **AC-001.7** Given tasks were created, when the service restarts, then `GET /tasks` returns 200 with `[]`.

## Non-goals

- Persistent storage, or tasks shared between several running instances of the service.
- Reading, updating, completing or deleting a single task.
- Filtering, sorting options or pagination of the list.
- Authentication and per-user task lists.
- Due times or time zones (a due date is a calendar date only).

## Assumptions

- **A1** Endpoints are `POST /tasks` and `GET /tasks`, fields `id`, `title`, `due_date` (other option: other paths or camelCase `dueDate`; affects AC-001.1, AC-001.2, AC-001.3).
- **A2** `due_date` is an ISO 8601 calendar date `YYYY-MM-DD`; any other form, including a date-time, is rejected with 422 (other option: accept date-times too; affects AC-001.1, AC-001.5).
- **A3** A due date in the past is accepted (other option: reject with 422; affects AC-001.5).
- **A4** A title is 1 to 200 characters and must contain a non-whitespace character; it is stored and returned exactly as sent (other option: trim surrounding whitespace, another length limit; affects AC-001.4).
- **A5** Validation errors use status 422 with the framework's standard error body (other option: 400 with a custom body; affects AC-001.4, AC-001.5).
- **A6** The list returns tasks oldest first, all of them, without a cap (other option: newest first, or a limit; affects AC-001.3).
- **A7** Ids are opaque server-assigned strings (for example UUIDs); a client-supplied `id` is ignored, as are other unknown fields (other option: sequential integers, or reject unknown fields; affects AC-001.1, AC-001.6).
- **A8** Duplicate titles are allowed (other option: reject with 409; affects AC-001.6).

## Open questions

## Changelog

- 2026-11-12 created
- 2026-11-12 approved
- 2026-11-12 building
- 2026-11-12 done
