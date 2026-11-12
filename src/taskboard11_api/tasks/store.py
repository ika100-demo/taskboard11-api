"""Thread-safe in-memory task store."""

import datetime
import threading
import uuid

from taskboard11_api.tasks.models import Task


class TaskStore:
    """Keeps tasks in creation order."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: list[Task] = []

    def add(self, title: str, due_date: datetime.date | None) -> Task:
        """Create a task with a fresh id and append it."""
        task = Task(id=str(uuid.uuid4()), title=title, due_date=due_date)
        with self._lock:
            self._tasks.append(task)
        return task

    def list(self) -> list[Task]:
        """Return a copy of all tasks in insertion order."""
        with self._lock:
            return list(self._tasks)
