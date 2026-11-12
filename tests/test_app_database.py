"""Wiring of the database and task store into the application."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from taskboard11_api.main import app
from taskboard11_api.tasks.api import get_task_store


def test_get_task_store_returns_app_state_store() -> None:
    application = FastAPI()
    sentinel = object()
    application.state.task_store = sentinel
    request = Request({"type": "http", "app": application, "headers": []})
    assert get_task_store(request) is sentinel


def test_each_startup_installs_new_database_and_store() -> None:
    with TestClient(app):
        first_store, first_db = app.state.task_store, app.state.database
    with TestClient(app):
        assert app.state.task_store is not first_store
        assert app.state.database is not first_db


def test_startup_without_database_succeeds(
    monkeypatch: pytest.MonkeyPatch, unreachable_database_url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", unreachable_database_url)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
