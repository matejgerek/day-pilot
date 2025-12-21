from langgraph.graph import END, StateGraph

from daypilot.settings import get_settings

settings = get_settings()
if not settings.openai_api_key:
    raise ValueError("OPENAI_API_KEY is not set")

# Import nodes after env is loaded so ChatOpenAI sees the key
from daypilot.start_nodes import (  # noqa: E402
    analyze_priorities_node,
    create_schedule_node,
    fetch_weather_node,
    fetch_whoop_node,
    gather_input_node,
    present_plan_node,
)
from daypilot.state import DayPlanState  # noqa: E402


def create_planning_agent():
    workflow = StateGraph(DayPlanState)
    workflow.add_node("gather_input", gather_input_node)
    workflow.add_node("fetch_weather", fetch_weather_node)
    workflow.add_node("fetch_whoop", fetch_whoop_node)
    workflow.add_node("analyze_priorities", analyze_priorities_node)
    workflow.add_node("create_schedule", create_schedule_node)
    workflow.add_node("present_plan", present_plan_node)

    # Define edges
    workflow.set_entry_point("gather_input")
    workflow.add_edge("gather_input", "fetch_weather")
    workflow.add_edge("fetch_weather", "fetch_whoop")
    workflow.add_edge("fetch_whoop", "analyze_priorities")
    workflow.add_edge("analyze_priorities", "create_schedule")
    workflow.add_edge("create_schedule", "present_plan")
    workflow.add_edge("present_plan", END)

    return workflow.compile()
