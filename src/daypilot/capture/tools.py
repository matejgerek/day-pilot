from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from daypilot.capture.schema import (
    CandidateTask,
    CandidateTaskValidationError,
    Confidence,
    Context,
    Depth,
    EstMinutes,
)
from daypilot.capture.state import CaptureState


class CandidateTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    context: Context
    est: EstMinutes
    depth: Depth
    dueISO: str | None = None
    notes: str | None = None
    confidence: Confidence


class CreateTasksArgs(BaseModel):
    tasks: list[CandidateTaskInput] = Field(min_length=1)


class CandidateTaskPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    context: Context | None = None
    est: EstMinutes | None = None
    depth: Depth | None = None
    dueISO: str | None = None
    notes: str | None = None
    confidence: Confidence | None = None


class EditTaskArgs(BaseModel):
    id: int
    patch: CandidateTaskPatch


class RemoveTaskArgs(BaseModel):
    id: int


@tool("create_tasks", args_schema=CreateTasksArgs)
def create_tasks_tool(tasks: list[CandidateTaskInput]) -> str:
    """Create one or more tasks from user input."""
    return f"Requested creation of {len(tasks)} task(s)."


@tool("edit_task", args_schema=EditTaskArgs)
def edit_task_tool(id: int, patch: CandidateTaskPatch) -> str:
    """Edit a task by id with a field patch."""
    return f"Requested edit for task {id}."


@tool("remove_task", args_schema=RemoveTaskArgs)
def remove_task_tool(id: int) -> str:
    """Remove a task by id."""
    return f"Requested removal of task {id}."


def tool_registry() -> dict[str, "ToolSpec"]:
    return {
        "create_tasks": ToolSpec(tool=create_tasks_tool, handler=_handle_create_tasks),
        "edit_task": ToolSpec(tool=edit_task_tool, handler=_handle_edit_task),
        "remove_task": ToolSpec(tool=remove_task_tool, handler=_handle_remove_task),
    }


@dataclass(frozen=True)
class ToolSpec:
    tool: BaseTool
    handler: Callable[[CaptureState, dict], str]


def apply_tool_calls(state: CaptureState, tool_calls: list[dict]) -> dict:
    registry = tool_registry()
    responses: list[ToolMessage] = []
    for call in tool_calls:
        name = call["name"]
        tool_call_id = call["id"]
        args = call.get("args", {})
        spec = registry.get(name)
        if spec is None:
            responses.append(
                ToolMessage(content=f"Unknown tool '{name}'.", tool_call_id=tool_call_id)
            )
            continue
        try:
            validated = spec.tool.args_schema.model_validate(args).model_dump()
            message = spec.handler(state, validated)
        except (ValidationError, CandidateTaskValidationError, ValueError) as exc:
            message = f"Tool '{name}' failed: {exc}"
        responses.append(ToolMessage(content=message, tool_call_id=tool_call_id))
    # IMPORTANT: LangGraph state updates are based on returned values.
    # Tool handlers mutate the passed-in state, so we must return the updated fields explicitly.
    return {"messages": responses, "tasks": state.get("tasks", [])}


def _handle_create_tasks(state: CaptureState, args: dict) -> str:
    tasks_input = args["tasks"]
    existing_ids = {task.id for task in state.get("tasks", [])}
    new_tasks: list[CandidateTask] = []
    next_id = _next_task_id(existing_ids)
    for task_input in tasks_input:
        payload = {
            "id": next_id,
            **task_input,
        }
        new_tasks.append(CandidateTask.model_validate(payload))
        existing_ids.add(next_id)
        next_id += 1

    state["tasks"] = [*state.get("tasks", []), *new_tasks]
    return f"Added {len(new_tasks)} task(s)."


def _handle_edit_task(state: CaptureState, args: dict) -> str:
    task_id = args["id"]
    patch = args["patch"]
    tasks = state.get("tasks", [])
    for index, task in enumerate(tasks):
        if task.id != task_id:
            continue
        payload = task.model_dump()
        patch_payload = {key: value for key, value in patch.items() if value is not None}
        if not patch_payload:
            raise ValueError("Patch must include at least one field.")
        payload.update(patch_payload)
        payload["id"] = task.id
        tasks[index] = CandidateTask.model_validate(payload)
        state["tasks"] = tasks
        return f"Updated task {task_id}."
    raise ValueError(f"No task found with id {task_id}.")


def _handle_remove_task(state: CaptureState, args: dict) -> str:
    task_id = args["id"]
    tasks = state.get("tasks", [])
    filtered = [task for task in tasks if task.id != task_id]
    if len(filtered) == len(tasks):
        raise ValueError(f"No task found with id {task_id}.")
    state["tasks"] = filtered
    return f"Removed task {task_id}."


def _next_task_id(existing_ids: set[int]) -> int:
    return max(existing_ids, default=0) + 1
