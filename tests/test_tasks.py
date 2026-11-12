"""Acceptance tests for spec 001 (create and list tasks in memory)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from taskboard11_api.main import app


@pytest.fixture()
def fresh() -> Any:
    """A client inside a `with` block: lifespan startup installs an empty store."""
    with TestClient(app) as c:
        yield c


def test_create_task_returns_201_with_fields(fresh: TestClient) -> None:  # AC-001.1
    r = fresh.post("/tasks", json={"title": "Buy milk", "due_date": "2026-12-01"})
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "title", "due_date"}
    assert isinstance(body["id"], str)
    assert body["id"]
    assert body["title"] == "Buy milk"
    assert body["due_date"] == "2026-12-01"


NO_DUE = [{"title": "Buy milk"}, {"title": "Buy milk", "due_date": None}]


@pytest.mark.parametrize("payload", NO_DUE)
def test_ac_001_2_create_task_without_due_date(fresh: TestClient, payload: dict[str, Any]) -> None:
    # AC-001.2
    r = fresh.post("/tasks", json=payload)
    assert r.status_code == 201
    assert r.json()["due_date"] is None


def test_list_tasks_in_creation_order(fresh: TestClient) -> None:  # AC-001.3
    created = [
        fresh.post("/tasks", json={"title": t, "due_date": d}).json()
        for t, d in [("A", "2026-01-01"), ("B", None), ("C", "2027-05-06")]
    ]
    r = fresh.get("/tasks")
    assert r.status_code == 200
    assert r.json() == created
    assert [t["title"] for t in r.json()] == ["A", "B", "C"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"due_date": "2026-12-01"},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"title": None},
        {"title": 5},
    ],
)
def test_ac_001_4_bad_title_is_422_not_stored(fresh: TestClient, payload: dict[str, Any]) -> None:
    # AC-001.4
    r = fresh.post("/tasks", json=payload)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)
    assert r.json()["detail"]
    assert r.json()["detail"][-1]["loc"][-1] == "title"
    assert fresh.get("/tasks").json() == []


def test_title_of_200_characters_is_accepted(fresh: TestClient) -> None:  # AC-001.4
    r = fresh.post("/tasks", json={"title": "x" * 200})
    assert r.status_code == 201


@pytest.mark.parametrize(
    "due", ["tomorrow", "2026-02-30", "2026-1-5", "2026-12-01T10:00:00", 20261201]
)
def test_ac_001_5_bad_due_date_is_422_not_stored(fresh: TestClient, due: Any) -> None:
    # AC-001.5
    r = fresh.post("/tasks", json={"title": "Buy milk", "due_date": due})
    assert r.status_code == 422
    assert r.json()["detail"]
    assert r.json()["detail"][0]["loc"][-1] == "due_date"
    assert fresh.get("/tasks").json() == []


def test_same_title_twice_gives_distinct_ids(fresh: TestClient) -> None:  # AC-001.6
    ra = fresh.post("/tasks", json={"title": "Same"})
    rb = fresh.post("/tasks", json={"title": "Same"})
    assert (ra.status_code, rb.status_code) == (201, 201)
    a, b = ra.json(), rb.json()
    listed = fresh.get("/tasks").json()
    assert [t["title"] for t in listed] == ["Same", "Same"]
    assert a["id"] != b["id"]
    assert {t["id"] for t in listed} == {a["id"], b["id"]}
