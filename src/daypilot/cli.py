import typer
from rich.console import Console

from daypilot.start import create_planning_agent
from daypilot.state import DayPlanState

app = typer.Typer()

console = Console()

@app.command()
def plan():
    """Create today's plan (test command)."""
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

def main():
    app()

if __name__ == "__main__":
    main()
