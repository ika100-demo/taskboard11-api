"""Unit tests for the task models."""

import datetime

import pytest
from pydantic import ValidationError

from taskboard11_api.tasks.models import Task, TaskCreate


def test_title_min_and_max_length_accepted() -> None:
    assert TaskCreate(title="a").title == "a"
    assert len(TaskCreate(title="a" * 200).title) == 200


@pytest.mark.parametrize("title", ["", "a" * 201])
def test_title_length_rejected(title: str) -> None:
    with pytest.raises(ValidationError):
        TaskCreate(title=title)


@pytest.mark.parametrize("title", [" ", "   ", "\t", "\n", " \t\n "])
def test_blank_title_rejected(title: str) -> None:
    with pytest.raises(ValidationError):
        TaskCreate(title=title)


@pytest.mark.parametrize("title", ["a\x00b", "\x00", "a\ud800b"])
def test_nul_and_unencodable_title_rejected(title: str) -> None:
    with pytest.raises(ValidationError):
        TaskCreate(title=title)


@pytest.mark.parametrize("title", [1, 1.5, True, None, ["a"], b"abc"])
def test_non_string_title_rejected(title: object) -> None:
    with pytest.raises(ValidationError):
        TaskCreate.model_validate({"title": title})


def test_missing_title_rejected() -> None:
    with pytest.raises(ValidationError):
        TaskCreate.model_validate({})


def test_title_is_not_trimmed() -> None:
    assert TaskCreate(title="  padded  ").title == "  padded  "


def test_due_date_defaults_to_none() -> None:
    assert TaskCreate(title="a").due_date is None


def test_due_date_explicit_none() -> None:
    assert TaskCreate.model_validate({"title": "a", "due_date": None}).due_date is None


def test_due_date_valid() -> None:
    model = TaskCreate.model_validate({"title": "a", "due_date": "2026-02-28"})
    assert model.due_date == datetime.date(2026, 2, 28)


@pytest.mark.parametrize(
    "value",
    [
        "2026-02-30",
        "2026-1-5",
        "2026-01-05T10:00:00",
        "2026-01-05 10:00:00",
        "2026-01-05T10:00:00Z",
        "20260105",
        "",
        "not-a-date",
        20260105,
        1.5,
        True,
        [],
        datetime.date(2026, 1, 5),
        datetime.datetime(2026, 1, 5, 10, 0),
    ],
)
def test_due_date_invalid_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        TaskCreate.model_validate({"title": "a", "due_date": value})


def test_unknown_fields_ignored() -> None:
    model = TaskCreate.model_validate({"title": "a", "id": "client-id", "extra": 1})
    assert model.title == "a"
    assert "id" not in model.model_dump()
    assert not hasattr(model, "extra")


def test_task_serializes_due_date_as_iso_string() -> None:
    task = Task(id="x", title="t", due_date=datetime.date(2026, 3, 4))
    assert task.model_dump(mode="json") == {
        "id": "x",
        "title": "t",
        "due_date": "2026-03-04",
    }


def test_task_serializes_missing_due_date_as_null() -> None:
    task = Task(id="x", title="t", due_date=None)
    assert task.model_dump(mode="json")["due_date"] is None
