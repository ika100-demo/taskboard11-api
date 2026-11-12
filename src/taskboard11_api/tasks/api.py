"""HTTP endpoints for tasks."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request

from .models import Task, TaskCreate
from .store import TaskStore

router = APIRouter()
logger = structlog.get_logger()


def get_task_store(request: Request) -> TaskStore:
    """Return the per-process task store."""
    store: TaskStore = request.app.state.task_store
    return store


StoreDep = Annotated[TaskStore, Depends(get_task_store)]


@router.post("/tasks", status_code=201, response_model=Task)
def create_task(body: TaskCreate, store: StoreDep) -> Task:
    """Create a task."""
    task = store.add(body.title, body.due_date)
    logger.info("task_created", task_id=task.id)
    return task


@router.get("/tasks", response_model=list[Task])
def list_tasks(store: StoreDep) -> list[Task]:
    """List all tasks, oldest first."""
    return store.list()
