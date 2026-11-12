"""PostgreSQL-backed task store."""

import datetime
import uuid

from taskboard11_api.db import Database
from taskboard11_api.tasks.models import Task


class TaskStore:
    """Stores tasks in the `tasks` table and lists them in creation order."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def add(self, title: str, due_date: datetime.date | None) -> Task:
        """Create a task with a fresh id and insert it."""
        task = Task(id=str(uuid.uuid4()), title=title, due_date=due_date)
        with self._database.connection() as conn:
            conn.execute(
                "INSERT INTO tasks (id, title, due_date) VALUES (%s, %s, %s)",
                (task.id, task.title, task.due_date),
            )
        return task

    def list(self) -> list[Task]:
        """Return all tasks in creation order."""
        with self._database.connection() as conn:
            rows = conn.execute("SELECT id, title, due_date FROM tasks ORDER BY seq").fetchall()
        return [Task(id=str(row[0]), title=row[1], due_date=row[2]) for row in rows]
