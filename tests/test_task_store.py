"""Unit tests for the Postgres-backed task store."""

import datetime
import threading
import uuid

import pytest

from taskboard11_api.db import Database, DatabaseUnavailableError
from taskboard11_api.tasks.store import TaskStore


def _store(url: str) -> TaskStore:
    return TaskStore(Database(url))


def test_new_store_is_empty(pg_server) -> None:  # type: ignore[no-untyped-def]
    assert _store(pg_server.url).list() == []


def test_add_returns_stored_task(pg_server) -> None:  # type: ignore[no-untyped-def]
    store = _store(pg_server.url)
    due = datetime.date(2026, 5, 1)
    task = store.add("write", due)
    assert (task.title, task.due_date) == ("write", due)
    assert store.list() == [task]


def test_order_preserved_across_stores(pg_server) -> None:  # type: ignore[no-untyped-def]
    titles = [f"t{i}" for i in range(20)]
    first = _store(pg_server.url)
    added = [first.add(title, None) for title in titles]
    assert [t.title for t in _store(pg_server.url).list()] == titles
    assert _store(pg_server.url).list() == added


def test_ids_are_distinct_uuids(pg_server) -> None:  # type: ignore[no-untyped-def]
    store = _store(pg_server.url)
    ids = [store.add("same", None).id for _ in range(20)]
    assert len(set(ids)) == 20
    for value in ids:
        assert str(uuid.UUID(value)) == value


def test_concurrent_adds(pg_server) -> None:  # type: ignore[no-untyped-def]
    store = _store(pg_server.url)
    threads_n, per_thread = 8, 10
    barrier = threading.Barrier(threads_n)
    errors: list[BaseException] = []

    def work() -> None:
        try:
            barrier.wait()
            for _ in range(per_thread):
                store.add("c", None)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    tasks = store.list()
    assert len(tasks) == threads_n * per_thread
    assert len({t.id for t in tasks}) == threads_n * per_thread


def test_unreachable_database_raises(unreachable_database_url: str) -> None:
    store = _store(unreachable_database_url)
    with pytest.raises(DatabaseUnavailableError):
        store.list()
    with pytest.raises(DatabaseUnavailableError):
        store.add("x", None)
