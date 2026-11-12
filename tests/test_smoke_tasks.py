"""Smoke tests for spec 001 (AC-001.1, AC-001.3): only the base URL, own data (`smoke-<uuid>`)."""

from __future__ import annotations

import uuid

import httpx
import pytest


@pytest.mark.smoke
@pytest.mark.writes
def test_ac_001_1_create_task_at_the_base_url(smoke_base_url: str) -> None:  # AC-001.1
    title = f"smoke-{uuid.uuid4()}"
    payload = {"title": title, "due_date": "2026-12-01"}
    r = httpx.post(smoke_base_url + "/tasks", json=payload, timeout=10)
    assert r.status_code == 201
    body = r.json()
    assert isinstance(body["id"], str)
    assert body["id"]
    assert body["title"] == title
    assert body["due_date"] == "2026-12-01"


@pytest.mark.smoke
@pytest.mark.writes
def test_ac_001_3_created_tasks_are_listed_in_order(smoke_base_url: str) -> None:  # AC-001.3
    titles = [f"smoke-{uuid.uuid4()}" for _ in range(3)]
    created = [
        httpx.post(smoke_base_url + "/tasks", json={"title": t}, timeout=10).json() for t in titles
    ]
    r = httpx.get(smoke_base_url + "/tasks", timeout=10)
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    positions = [ids.index(c["id"]) for c in created]
    assert positions == sorted(positions)
    assert len(set(positions)) == 3


@pytest.mark.smoke
def test_ac_001_3_list_tasks_is_readable(smoke_base_url: str) -> None:  # AC-001.3 (read-only)
    r = httpx.get(smoke_base_url + "/tasks", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.smoke
def test_ac_001_1_invalid_task_is_rejected(smoke_base_url: str) -> None:
    # AC-001.1 (read-only: nothing stored)
    r = httpx.post(smoke_base_url + "/tasks", json={"title": ""}, timeout=10)
    assert r.status_code == 422
