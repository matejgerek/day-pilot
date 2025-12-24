from __future__ import annotations

from datetime import datetime
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from daypilot.capture.schema import CandidateTask
from daypilot.capture.state import CaptureState
from daypilot.capture.tools import apply_tool_calls, tool_registry

load_dotenv()

llm = ChatOpenAI(model="gpt-5-mini", reasoning_effort="low", streaming=True)


def create_capture_agent():
    tools = [spec.tool for spec in tool_registry().values()]
    llm_with_tools = llm.bind_tools(tools)

    async def llm_call(state: CaptureState, *, config: RunnableConfig) -> CaptureState:
        now = state.get("now") or datetime.now().astimezone()
        system_prompt = _system_prompt(now, state.get("tasks", []))
        response = await llm_with_tools.ainvoke(
            [SystemMessage(content=system_prompt)] + state["messages"],
            config=config,
        )
        return {"messages": [response], "now": now}

    def tool_node(state: CaptureState) -> CaptureState:
        last_message = state["messages"][-1]
        return apply_tool_calls(state, last_message.tool_calls)

    def should_continue(state: CaptureState) -> Literal["tool_node", END]:
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tool_node"
        return END

    builder = StateGraph(CaptureState)
    builder.add_node("llm_call", llm_call)
    builder.add_node("tool_node", tool_node)
    builder.add_edge(START, "llm_call")
    builder.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
    builder.add_edge("tool_node", "llm_call")

    return builder.compile()


def _system_prompt(now: datetime, tasks: list[CandidateTask]) -> str:
    now_str = now.strftime("%A, %Y-%m-%d %H:%M")
    tasks_block = _format_tasks(tasks)
    return f"""You are a capture agent.
Your job: convert messy user input into a clean list of tasks.

Current local time: {now_str}

## Core behavior
- Be decisive: extract tasks and propose metadata.
- The user will review/edit later; create good candidates fast.

## Candidate Task schema (must be complete)
Each candidate task MUST include:
- title: short imperative, <= 80 chars (e.g. "Reply to Andrej about spec")
- context: work or personal
- est: one of [10, 25, 45, 90] minutes (bucketed)
- depth: shallow or deep
- confidence: low / med / high
Optional:
- dueISO: YYYY-MM-DD only if user implies a deadline/date.
- notes: only execution-critical clarifications (1 short sentence).

## Estimation rules (required)
- quick message/reply/schedule/pay/small admin: est=10
- small focused work/write short doc/review PR: est=25 or 45
- deep work/implement feature/write long doc: est=90
- if unsure: pick closest bucket and lower confidence; do NOT ask

## Depth rules (required)
- deep: uninterrupted focus (writing, coding, design, studying, analysis)
- shallow: can be done in fragments (messages, scheduling, errands, admin)

## Context rules (required)
- work: job/client/team/dev, professional deliverables
- personal: life admin, health, errands, relationships, purchases
- if unclear after inference: ask a concise clarifying question

## Due date rules (important)
- add dueISO only when user gives a clear time reference
- convert 'today/tomorrow/weekday' to ISO based on current local time
- otherwise omit dueISO (do not invent dates)

## Notes rules (important)
- notes are not a description; only include what changes execution
- no step-by-step plans; break down into separate tasks instead

## Dedupe & cleanup
- avoid duplicates; keep only the best title
- split only when clearly separate actions

## Tool use
- for a brain dump / adding tasks: call create_tasks once with all tasks.
- for changes: use edit_task/remove_task via id
- if you need clarification: ask before calling a tool

## Responses
- be concise and to the point
- do not print the entire task list, since the user sees it in the UI, unless asked to do so

Current tasks:
{tasks_block}
"""


def _format_tasks(tasks: list[CandidateTask]) -> str:
    if not tasks:
        return "- (none)"
    lines: list[str] = []
    for task in tasks:
        due = task.dueISO or "none"
        notes = task.notes or "none"
        lines.append(
            f"- {task.id}: {task.title} | {task.context.value} | {task.est}m | "
            f"{task.depth.value} | due {due} | confidence {task.confidence.value} | notes {notes}"
        )
    return "\n".join(lines)
