import json

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from daypilot.services.weather import WeatherService
from daypilot.services.whoop_data import WhoopSnapshot
from daypilot.state import DayPlanState


class ScheduledBlock(BaseModel):
    start_time: str = Field(
        description="Block start time in HH:MM 24-hour format.",
    )
    end_time: str = Field(
        description="Block end time in HH:MM 24-hour format.",
    )
    task: str = Field(
        description="Task, commitment, or break description for the block.",
    )
    is_fixed: bool = Field(
        description="True when the block is an immovable fixed commitment.",
    )


class SchedulePlan(BaseModel):
    schedule: list[ScheduledBlock] = Field(
        description="Ordered list of time blocks for the day.",
    )
    strategy: str = Field(
        description="Brief rationale for ordering, buffers, and energy management.",
    )


llm = ChatOpenAI(model="gpt-5-mini", reasoning_effort="low")
scheduler = llm.with_structured_output(SchedulePlan)


def create_schedule_node(state: DayPlanState) -> DayPlanState:
    """Generate time-blocked schedule"""
    tasks_json = json.dumps(state["tasks"], indent=2)
    commitments_text = "\n".join(f"- {c}" for c in state["fixed_commitments"]) or "None"
    now_str = state["now"].strftime("%A, %B %d, %Y at %I:%M %p")

    prompt = f"""Create a time-blocked schedule for the workday.

Current date and time: {now_str}
Work hours: {state["work_hours"]}
Available hours: {state["total_available_hours"]}

Fixed commitments:
{commitments_text}

{_weather_prompt(state)}
{_whoop_prompt(state)}

Tasks to schedule:
{tasks_json}

Rules:
1. Schedule non-negotiables in prime focus time (usually morning)
2. Add buffer time for unexpected issues
3. Include breaks (lunch, short breaks)
4. Work around fixed commitments
5. Be realistic about energy levels throughout the day

Return a realistic schedule with precise start/end times and flag fixed commitments."""

    response = scheduler.invoke(prompt)

    state["schedule"] = [block.model_dump() for block in response.schedule]
    state["messages"].append({"role": "user", "content": prompt})
    state["messages"].append({"role": "assistant", "content": response.model_dump_json()})

    return state


def _weather_prompt(state: DayPlanState) -> str:
    weather_data = state.get("weather")
    if not weather_data:
        return "Weather: Unavailable."
    service = WeatherService()
    return service.format_from_dict(weather_data)


def _whoop_prompt(state: DayPlanState) -> str:
    whoop_data = state.get("whoop")
    if not whoop_data:
        return "WHOOP: Unavailable."
    try:
        snapshot = WhoopSnapshot.from_dict(whoop_data)
    except Exception:
        return "WHOOP: Unavailable."
    return snapshot.format_for_prompt()
