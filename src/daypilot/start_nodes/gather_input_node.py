from datetime import datetime

from rich.console import Console
from rich.prompt import Prompt

from daypilot.state import DayPlanState

console = Console()


def gather_input_node(state: DayPlanState) -> DayPlanState:
    today_str = datetime.now().strftime("%A, %B %d, %Y")
    console.print(
        "\n[bold blue]📅 Today is "
        f"{today_str}"
        "[/bold blue]\n",
    )
    
    # Gather priorities
    console.print("What are your top priorities for today?")
    console.print("[dim](Enter one per line, empty line when done)[/dim]")

    priorities = []
    while True:
        priority = Prompt.ask(">")
        if not priority:
            break
        priorities.append(priority)
    
    # Gather work hours
    work_hours = Prompt.ask("\n⏰ What hours are you working today?", default="9am-6pm")

    # Gather commitments
    console.print("\n🚫 Any fixed commitments? (meetings, gym time, etc.)")
    console.print("[dim](Enter one per line, empty line when done)[/dim]")
    
    commitments = []
    while True:
        commitment = Prompt.ask(">", default="")
        if not commitment:
            break
        commitments.append(commitment)
    
    # Update state
    state["priorities"] = priorities
    state["work_hours"] = work_hours
    state["fixed_commitments"] = commitments
    
    return state
