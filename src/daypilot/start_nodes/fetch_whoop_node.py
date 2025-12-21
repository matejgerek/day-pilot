from rich.console import Console

from daypilot.services.config import ConfigMissingError, load_config
from daypilot.services.whoop_data import WhoopDataService, WhoopServiceError
from daypilot.state import DayPlanState

console = Console()


def fetch_whoop_node(state: DayPlanState) -> DayPlanState:
    try:
        config = load_config()
    except ConfigMissingError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        state["whoop"] = None
        return state

    if not config.whoop:
        console.print("[yellow]WHOOP not connected. Run `cli whoop-connect` first.[/yellow]")
        state["whoop"] = None
        return state

    service = WhoopDataService(config.whoop)
    try:
        snapshot = service.get_snapshot()
    except WhoopServiceError as exc:
        console.print(f"[yellow]WHOOP unavailable: {exc}[/yellow]")
        state["whoop"] = None
        return state

    state["whoop"] = snapshot.to_dict()
    return state
