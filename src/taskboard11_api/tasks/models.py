"""Request and response models for tasks."""

import datetime
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TaskCreate(BaseModel):
    """Request body for creating a task."""

    title: str = Field(min_length=1, max_length=200, strict=True)
    due_date: datetime.date | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must contain a non-whitespace character")
        return value

    @field_validator("due_date", mode="before")
    @classmethod
    def _due_date_strict(cls, value: Any) -> datetime.date | None:
        if value is None:
            return None
        if not isinstance(value, str) or not _DATE_RE.match(value):
            raise ValueError("due_date must be a string in the form YYYY-MM-DD")
        return datetime.date.fromisoformat(value)


class Task(BaseModel):
    """A stored task, also the response body."""

    id: str
    title: str
    due_date: datetime.date | None
