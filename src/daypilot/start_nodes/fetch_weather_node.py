from rich.console import Console

from daypilot.services.config import ConfigMissingError, load_config
from daypilot.services.weather import WeatherService, WeatherServiceError
from daypilot.state import DayPlanState

console = Console()


def fetch_weather_node(state: DayPlanState) -> DayPlanState:
    try:
        config = load_config()
    except ConfigMissingError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        state["weather"] = None
        return state

    service = WeatherService()
    try:
        report = service.fetch(config.location, state["now"])
    except WeatherServiceError as exc:
        console.print(f"[yellow]Weather unavailable: {exc}[/yellow]")
        state["weather"] = None
        return state

    state["weather"] = report.to_dict()
    return state
