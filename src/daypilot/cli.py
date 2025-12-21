import typer
from rich.console import Console

from daypilot.start import create_planning_agent
from daypilot.state import DayPlanState

app = typer.Typer()

console = Console()


@app.command()
def plan():
    """Create today's plan (test command)."""
    from daypilot.services.config import ConfigMissingError, load_config

    try:
        load_config()
    except ConfigMissingError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    header_lines = [
        "[bold blue]╔══════════════════════════════════════════════════════════╗[/bold blue]",
        "[bold blue]║  🎯 DayPilot - Your Adaptive Workday Co-pilot            ║[/bold blue]",
        "[bold blue]╚══════════════════════════════════════════════════════════╝[/bold blue]",
    ]
    console.print()
    for line in header_lines:
        console.print(line)
    console.print()

    agent = create_planning_agent()

    initial_state = DayPlanState(
        priorities=[],
        work_hours="",
        fixed_commitments=[],
    )

    final_state = agent.invoke(initial_state)
    console.print(final_state)


@app.command()
def execute():
    """Execute today's plan (test command)."""
    typer.echo("Executing...")


@app.command()
def init():
    """Initialize local settings (location only)."""
    from daypilot.services.config import (
        AppConfig,
        ConfigMissingError,
        LocationConfig,
        load_config,
        write_config,
    )
    from daypilot.services.location_normalization import (
        LocationNormalizationError,
        LocationNormalizer,
    )

    console.print("[bold blue]DayPilot setup[/bold blue]")
    normalizer = LocationNormalizer()

    try:
        existing_config = load_config()
        existing_location = existing_config.location
    except ConfigMissingError:
        existing_location = None

    while True:
        prompt = "Enter your location (city/region)"
        default_value = existing_location.canonical_name if existing_location else None
        raw_location = typer.prompt(prompt, default=default_value)

        if existing_location and raw_location == existing_location.canonical_name:
            console.print(
                f"[green]Keeping existing location: {existing_location.canonical_name}[/green]"
            )
            return

        try:
            normalized = normalizer.resolve(raw_location)
        except LocationNormalizationError as exc:
            console.print(f"[red]Could not resolve location: {exc}[/red]")
            if not typer.confirm("Try again?", default=True):
                return
            continue

        if not normalized.canonical_name:
            console.print("[red]Could not resolve a canonical location name.[/red]")
            if not typer.confirm("Try again?", default=True):
                return
            continue

        console.print(f"I found: [bold]{normalized.canonical_name}[/bold]")
        if typer.confirm("Use this location?", default=True):
            config = AppConfig(
                location=LocationConfig(
                    canonical_name=normalized.canonical_name,
                    city=normalized.city,
                    region=normalized.region,
                    country=normalized.country,
                    latitude=normalized.latitude,
                    longitude=normalized.longitude,
                    timezone=normalized.timezone,
                )
            )
            write_config(config)
            console.print(f"[green]Location set to {normalized.canonical_name}[/green]")
            console.print(f"Coordinates: {normalized.latitude}, {normalized.longitude}")
            if normalized.timezone:
                console.print(f"Timezone: {normalized.timezone}")
            return


def main():
    app()


if __name__ == "__main__":
    main()
