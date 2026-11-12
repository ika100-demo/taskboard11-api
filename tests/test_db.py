"""Unit tests for the Database module against a real PostgreSQL."""

from __future__ import annotations

import time

import psycopg
import pytest
from conftest import PgServer

from taskboard11_api.db import Database, DatabaseUnavailableError


def _has_tasks_table(url: str) -> bool:
    with psycopg.connect(url) as conn:
        row = conn.execute("SELECT to_regclass('public.tasks')").fetchone()
    return bool(row and row[0] is not None)


def test_schema_created_on_empty_database_and_idempotent(pg_server: PgServer) -> None:
    url = pg_server.create_database()
    assert not _has_tasks_table(url)
    Database(url).ensure_schema()
    assert _has_tasks_table(url)
    Database(url).ensure_schema()  # a second start keeps working
    db = Database(url)
    db.ensure_schema()
    db.ensure_schema()
    assert _has_tasks_table(url)


def test_schema_keeps_existing_rows(pg_server: PgServer) -> None:
    url = pg_server.create_database()
    Database(url).ensure_schema()
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("INSERT INTO tasks (id, title) VALUES (gen_random_uuid(), %s)", ("keep me",))
    Database(url).ensure_schema()
    with psycopg.connect(url) as conn:
        row = conn.execute("SELECT count(*) FROM tasks").fetchone()
    assert row is not None and row[0] == 1


def test_is_ready_true(pg_server: PgServer) -> None:
    assert Database(pg_server.create_database()).is_ready() is True


def test_is_ready_false_when_unreachable(unreachable_database_url: str) -> None:
    assert Database(unreachable_database_url).is_ready() is False


def test_is_ready_false_when_hanging(hanging_database_url: str) -> None:
    start = time.monotonic()
    assert Database(hanging_database_url).is_ready() is False
    assert time.monotonic() - start < 5


@pytest.mark.parametrize("value", [None, ""])
def test_is_ready_false_without_url(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", value)
    db = Database()
    assert db.is_ready() is False
    with pytest.raises(DatabaseUnavailableError):
        with db.connection():
            pass


def test_connection_raises_unavailable_when_unreachable(unreachable_database_url: str) -> None:
    with pytest.raises(DatabaseUnavailableError):
        with Database(unreachable_database_url).connection():
            pass


def test_connection_commits_and_rolls_back(pg_server: PgServer) -> None:
    db = Database(pg_server.create_database())
    with db.connection() as conn:
        conn.execute("INSERT INTO tasks (id, title) VALUES (gen_random_uuid(), 'a')")
    with pytest.raises(RuntimeError):
        with db.connection() as conn:
            conn.execute("INSERT INTO tasks (id, title) VALUES (gen_random_uuid(), 'b')")
            raise RuntimeError("boom")
    with db.connection() as conn:
        row = conn.execute("SELECT count(*) FROM tasks").fetchone()
    assert row is not None and row[0] == 1


def test_recovers_after_server_restart(pg_server: PgServer) -> None:
    db = Database(pg_server.create_database())
    assert db.is_ready() is True
    try:
        pg_server.stop()
        assert db.is_ready() is False
        with pytest.raises(DatabaseUnavailableError):
            with db.connection():
                pass
    finally:
        pg_server.ensure_running()
    assert db.is_ready() is True
