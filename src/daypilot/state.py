from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import MessagesState


class Task(TypedDict):
    title: str
    duration_hours: float
    is_non_negotiable: bool


class TimeBlock(TypedDict):
    start_time: str
    end_time: str
    task: str
    is_fixed: bool


class DayPlanState(MessagesState):
    # Inputs
    priorities: list[str]
    work_hours: str  # e.g., "9am-5pm"
    fixed_commitments: list[str]
    now: datetime

    # Processed data
    total_available_hours: float
    tasks: list[Task]
    schedule: list[TimeBlock]
    non_negotiables: list[str]
    nice_to_haves: list[str]
    weather: dict[str, Any] | None
