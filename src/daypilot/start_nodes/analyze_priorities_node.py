from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from rich.console import Console

from daypilot.services.whoop_data import WhoopSnapshot
from daypilot.state import DayPlanState

console = Console()

llm = ChatOpenAI(model="gpt-5-mini", reasoning_effort="low")


class NonNegotiableTask(BaseModel):
    title: str = Field(
        description="Name of the task.",
    )
    duration_hours: float = Field(
        description="Estimated time needed in hours.",
    )
    reasoning: str = Field(
        description="Why this task is critical and must be completed today.",
    )


class NiceToHaveTask(BaseModel):
    title: str = Field(
        description="Name of the task.",
    )
    duration_hours: float = Field(
        description="Estimated time needed in hours.",
    )


class PrioritiesAnalysis(BaseModel):
    non_negotiables: list[NonNegotiableTask] = Field(
        description="Tasks that must be completed today.",
    )
    nice_to_haves: list[NiceToHaveTask] = Field(
        description="Tasks that would be good to complete if time allows.",
    )
    total_available_hours: float = Field(
        description="Total hours available for work today.",
    )
    strategy_note: str = Field(
        description="Brief note about the planning strategy.",
    )


analyzer = llm.with_structured_output(PrioritiesAnalysis)


def analyze_priorities_node(state: DayPlanState) -> DayPlanState:
    console.print("\n[bold blue]Analyzing your day...[/bold blue]")

    priorities_text = "\n".join(state["priorities"])
    commitments_text = "\n".join(state["fixed_commitments"])
    now_str = state["now"].strftime("%A, %B %d, %Y at %I:%M %p")

    prompt = f"""You are a productivity assistant helping someone plan their workday.

Current date and time: {now_str}
Work hours: {state["work_hours"]}
Fixed commitments:
{commitments_text if commitments_text else "None"}

Health context:
{_whoop_prompt(state)}

Priorities:
{priorities_text}

Your task:
1. Identify 2-3 "non-negotiable" tasks that MUST be completed today
2. Categorize remaining tasks as "nice-to-have"
3. Estimate realistic time needed for each task (in hours)
4. Calculate total available work hours after accounting for commitments
"""
    response = analyzer.invoke(prompt)

    result = response.model_dump()

    # Update state
    state["non_negotiables"] = [task["title"] for task in result["non_negotiables"]]
    state["nice_to_haves"] = [task["title"] for task in result["nice_to_haves"]]
    state["total_available_hours"] = result["total_available_hours"]

    # Store all tasks
    state["tasks"] = result["non_negotiables"] + result["nice_to_haves"]

    # Store messages for context
    state["messages"] = [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": response.model_dump_json()},
    ]

    return state


def _whoop_prompt(state: DayPlanState) -> str:
    whoop_data = state.get("whoop")
    if not whoop_data:
        return "WHOOP: Unavailable."
    try:
        snapshot = WhoopSnapshot.from_dict(whoop_data)
    except Exception:
        return "WHOOP: Unavailable."
    return snapshot.format_for_prompt()
