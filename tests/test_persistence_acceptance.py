"""Acceptance tests for spec 002 (store tasks in PostgreSQL so they survive)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from taskboard11_api.main import app

if TYPE_CHECKING:
    from conftest import PgServer

UNAVAILABLE = {"detail": "database unavailable"}


def _wait_ready(c: TestClient, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if c.get("/ready").status_code == 200:
            return True
        time.sleep(0.25)
    return False


def test_tasks_survive_restart_in_creation_order() -> None:  # AC-002.1
    with TestClient(app) as first:
        created = [
            first.post("/tasks", json={"title": t, "due_date": d}).json()
            for t, d in [("A", "2026-01-01"), ("B", None), ("C", "2027-05-06")]
        ]
        assert all("id" in c for c in created)
    with TestClient(app) as second:
        r = second.get("/tasks")
        assert r.status_code == 200
        listed = r.json()
        assert [(t["id"], t["title"], t["due_date"]) for t in listed] == [
            (c["id"], c["title"], c["due_date"]) for c in created
        ]
        assert [t["title"] for t in listed] == ["A", "B", "C"]


def test_empty_database_gets_schema_and_keeps_tasks_on_second_start(
    pg_server: PgServer, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC-002.2
    monkeypatch.setenv("DATABASE_URL", pg_server.create_database())
    with TestClient(app) as first:
        assert first.get("/ready").status_code == 200
        r = first.post("/tasks", json={"title": "Buy milk", "due_date": "2026-12-01"})
        assert r.status_code == 201
        created = r.json()
        assert first.get("/tasks").json() == [created]
    with TestClient(app) as second:
        r = second.get("/tasks")
        assert r.status_code == 200
        assert r.json() == [created]


@pytest.mark.parametrize("failure", ["unreachable", "hanging"])
def test_unreachable_database_answers_503(
    failure: str,
    unreachable_database_url: str,
    hanging_database_url: str,
    pg_server: PgServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # AC-002.3
    with TestClient(app) as c:
        # Start healthy, then point the service at a database that is gone.
        monkeypatch.setenv(
            "DATABASE_URL",
            unreachable_database_url if failure == "unreachable" else hanging_database_url,
        )
        for method, path, kwargs in [
            ("post", "/tasks", {"json": {"title": "Buy milk"}}),
            ("get", "/tasks", {}),
            ("get", "/ready", {}),
        ]:
            started = time.monotonic()
            r = getattr(c, method)(path, **kwargs)
            assert time.monotonic() - started < 5, path
            assert r.status_code == 503, path
            if path == "/ready":
                assert r.json() == {"status": "unavailable"}
            else:
                assert r.json() == UNAVAILABLE
        assert c.get("/health").status_code == 200


def test_ready_recovers_and_outage_task_is_not_stored(pg_server: PgServer) -> None:  # AC-002.4
    with TestClient(app) as c:
        assert c.post("/tasks", json={"title": "before"}).status_code == 201
        pg_server.stop()
        try:
            r = c.post("/tasks", json={"title": "during outage"})
            assert r.status_code == 503
            assert r.json() == UNAVAILABLE
            assert c.get("/ready").status_code == 503
        finally:
            pg_server.start()
        assert _wait_ready(c, 10), "GET /ready did not return 200 within 10 s"
        r = c.get("/tasks")
        assert r.status_code == 200
        titles = [t["title"] for t in r.json()]
        assert "during outage" not in titles
        assert titles == ["before"]


def test_database_down_at_start_keeps_process_up(
    unreachable_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC-002.5
    monkeypatch.setenv("DATABASE_URL", unreachable_database_url)
    with TestClient(app) as c:
        health = c.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        assert c.get("/ready").status_code == 503
        post: Any = c.post("/tasks", json={"title": "Buy milk"})
        assert post.status_code == 503
        assert post.json() == UNAVAILABLE
        listing = c.get("/tasks")
        assert listing.status_code == 503
        assert listing.json() == UNAVAILABLE
