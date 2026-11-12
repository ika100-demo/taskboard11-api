"""Unit tests for the task store, its dependency and the app lifespan."""

import datetime
import threading
import uuid
from types import SimpleNamespace
from typing import Any, cast

from fastapi import Request
from fastapi.testclient import TestClient

from taskboard11_api.main import app
from taskboard11_api.tasks.api import get_task_store
from taskboard11_api.tasks.store import TaskStore


def test_new_store_is_empty() -> None:
    assert TaskStore().list() == []


def test_add_returns_stored_task() -> None:
    store = TaskStore()
    due = datetime.date(2026, 5, 1)
    task = store.add("write", due)
    assert (task.title, task.due_date) == ("write", due)
    assert store.list() == [task]


def test_insertion_order_preserved() -> None:
    store = TaskStore()
    titles = [f"t{i}" for i in range(20)]
    for title in titles:
        store.add(title, None)
    assert [t.title for t in store.list()] == titles


def test_ids_are_distinct_uuids() -> None:
    store = TaskStore()
    ids = [store.add("same", None).id for _ in range(50)]
    assert len(set(ids)) == 50
    for value in ids:
        assert str(uuid.UUID(value)) == value


def test_list_returns_a_copy() -> None:
    store = TaskStore()
    store.add("a", None)
    snapshot = store.list()
    snapshot.clear()
    assert len(store.list()) == 1
    store.add("b", None)
    assert len(snapshot) == 0


def test_stores_are_independent() -> None:
    first, second = TaskStore(), TaskStore()
    first.add("a", None)
    assert second.list() == []


def test_concurrent_add_is_thread_safe() -> None:
    store = TaskStore()
    threads_n, per_thread = 16, 200
    barrier = threading.Barrier(threads_n)

    def work() -> None:
        barrier.wait()
        for _ in range(per_thread):
            store.add("c", None)
            store.list()

    threads = [threading.Thread(target=work) for _ in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    tasks = store.list()
    assert len(tasks) == threads_n * per_thread
    assert len({t.id for t in tasks}) == threads_n * per_thread


def test_get_task_store_returns_app_state_store() -> None:
    store = TaskStore()
    request = cast(
        Request,
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(task_store=store))),
    )
    assert get_task_store(request) is store


def test_lifespan_installs_fresh_store_on_each_startup() -> None:
    stores: list[Any] = []
    for _ in range(2):
        with TestClient(app) as client:
            store = app.state.task_store
            assert isinstance(store, TaskStore)
            assert store.list() == []
            client.post("/tasks", json={"title": "x"})
            assert len(store.list()) == 1
            stores.append(store)
    assert stores[0] is not stores[1]
