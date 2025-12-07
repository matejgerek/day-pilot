
from langgraph.graph import END, StateGraph

from daypilot.state import DayPlanState
from daypilot.start_nodes import (
    analyze_priorities_node,
    create_schedule_node,
    gather_input_node,
    present_plan_node,
)

def create_planning_agent():
    workflow = StateGraph(DayPlanState)
    workflow.add_node("gather_input", gather_input_node)
    workflow.add_node("analyze_priorities", analyze_priorities_node)
    workflow.add_node("create_schedule", create_schedule_node)
    workflow.add_node("present_plan", present_plan_node)

    # Define edges
    workflow.set_entry_point("gather_input")
    workflow.add_edge("gather_input", "analyze_priorities")
    workflow.add_edge("analyze_priorities", "create_schedule")
    workflow.add_edge("create_schedule", "present_plan")
    workflow.add_edge("present_plan", END)

    return workflow.compile()
