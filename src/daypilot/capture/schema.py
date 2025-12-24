from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

EstMinutes = Literal[10, 25, 45, 90]


class Context(StrEnum):
    WORK = "work"
    PERSONAL = "personal"


class Depth(StrEnum):
    SHALLOW = "shallow"
    DEEP = "deep"


class Confidence(StrEnum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


class CandidateTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(description="Short numeric ID for chat references.")
    title: str = Field(description="Imperative, concise task title.")
    context: Context
    est: EstMinutes
    depth: Depth
    dueISO: str | None = Field(default=None, description="Due date in YYYY-MM-DD format.")
    notes: str | None = None
    confidence: Confidence

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("id must be a positive integer")
        return value

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must be a non-empty string")
        return value

    @field_validator("notes")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("dueISO")
    @classmethod
    def _validate_due_iso(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("dueISO must be in YYYY-MM-DD format") from exc
        return value


class CandidateTaskValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


def validate_candidate_tasks(payloads: Iterable[dict]) -> list[CandidateTask]:
    tasks: list[CandidateTask] = []
    errors: list[str] = []
    for index, payload in enumerate(payloads):
        try:
            tasks.append(CandidateTask.model_validate(payload))
        except ValidationError as exc:
            errors.append(f"Task {index + 1}: {exc}")
    if errors:
        raise CandidateTaskValidationError(errors)
    return tasks
