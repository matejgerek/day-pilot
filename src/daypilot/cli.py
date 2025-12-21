from datetime import datetime, timezone

import typer
from rich.console import Console

from daypilot.state import DayPlanState

app = typer.Typer()

console = Console()


@app.command()
def plan():
    """Create today's plan (test command)."""
    from daypilot.services.config import ConfigMissingError, load_config
    from daypilot.start import create_planning_agent

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


@app.command("whoop-connect")
def whoop_connect(
    scope: str = typer.Option(None, help="Override WHOOP OAuth scope."),
):
    """Connect your WHOOP account."""
    from daypilot.services.config import AppConfig, ConfigMissingError, load_config, write_config
    from daypilot.services.whoop_oauth import DEFAULT_SCOPE, WhoopOAuthError, WhoopOAuthService
    from daypilot.settings import get_settings

    try:
        existing_config = load_config()
    except ConfigMissingError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    if existing_config.whoop and not typer.confirm(
        "WHOOP is already connected. Reconnect?", default=False
    ):
        return

    settings = get_settings()
    if not settings.whoop_client_id or not settings.whoop_client_secret:
        console.print(
            "[red]WHOOP credentials missing. Set WHOOP_CLIENT_ID and "
            "WHOOP_CLIENT_SECRET in your .env.[/red]"
        )
        return

    service = WhoopOAuthService(settings.whoop_client_id, settings.whoop_client_secret)
    console.print(
        "Opening WHOOP authorization in your browser. "
        f"Make sure your redirect URL is set to {service.redirect_uri}."
    )

    try:
        whoop_config = service.connect(scope=scope or DEFAULT_SCOPE)
    except WhoopOAuthError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    updated = AppConfig(location=existing_config.location, whoop=whoop_config)
    write_config(updated)
    console.print("[green]WHOOP connected successfully.[/green]")


@app.command("whoop-status")
def whoop_status():
    """Show WHOOP connection status."""
    from daypilot.services.config import ConfigMissingError, load_config

    try:
        config = load_config()
    except ConfigMissingError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    if not config.whoop:
        console.print("WHOOP is not connected.")
        return

    whoop = config.whoop
    now = datetime.now(timezone.utc)
    expires_at = whoop.expires_at.isoformat() if whoop.expires_at else "Unknown"
    status = "expired" if whoop.expires_at and whoop.expires_at <= now else "active"
    connected_at = whoop.connected_at.isoformat()
    last_sync = whoop.last_sync_at.isoformat() if whoop.last_sync_at else "Not yet"

    console.print(f"WHOOP connection: {status}")
    console.print(f"Connected at: {connected_at}")
    console.print(f"Access token expires at: {expires_at}")
    console.print(f"Last sync: {last_sync}")


@app.command("whoop-disconnect")
def whoop_disconnect():
    """Disconnect WHOOP and remove stored credentials."""
    from daypilot.services.config import AppConfig, ConfigMissingError, load_config, write_config

    try:
        config = load_config()
    except ConfigMissingError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    if not config.whoop:
        console.print("WHOOP is not connected.")
        return

    if not typer.confirm("Disconnect WHOOP and remove credentials?", default=False):
        return

    updated = AppConfig(location=config.location, whoop=None)
    write_config(updated)
    console.print("[green]WHOOP disconnected.[/green]")


def main():
    app()


if __name__ == "__main__":
    main()
