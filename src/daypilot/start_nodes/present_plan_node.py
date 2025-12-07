import json

from daypilot.state import DayPlanState


def present_plan_node(state: DayPlanState) -> DayPlanState:
    """Display the final plan to user"""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    
    console = Console()
    
    # Summary panel
    summary = f"""
📋 Your Day Plan

Available: {state['total_available_hours']} hours

⚡ NON-NEGOTIABLES (must complete):
{chr(10).join(f"  {i+1}. {task}" for i, task in enumerate(state['non_negotiables']))}

📌 NICE-TO-HAVE:
{chr(10).join(f"  {i+1}. {task}" for i, task in enumerate(state['nice_to_haves']))}

✅ ALREADY SCHEDULED:
{chr(10).join(f"  • {c}" for c in state['fixed_commitments'])}
"""
    
    console.print(Panel(summary, border_style="blue"))
    
    # Schedule table
    table = Table(title="🕐 TIME-BLOCKED SCHEDULE", show_header=True)
    table.add_column("Time", style="cyan", width=20)
    table.add_column("Task", style="white")
    
    for block in state["schedule"]:
        time_range = f"{block['start_time']} - {block['end_time']}"
        task = block['task']
        if block['is_fixed']:
            task = f"🔒 {task}"
        table.add_row(time_range, task)
    
    console.print(table)

    
    # Strategy note
    if state["messages"]:
        last_message = state["messages"][-1]
        content = getattr(last_message, "content", None)
        if content is None and isinstance(last_message, dict):
            content = last_message.get("content")

        strategy = None
        if isinstance(content, str):
            try:
                strategy = json.loads(content).get("strategy")
            except json.JSONDecodeError:
                pass
        elif isinstance(content, dict):
            strategy = content.get("strategy")

        if strategy:
            console.print(f"\n💡 Strategy: {strategy}\n")
    
    console.print("[bold green]Ready to start? Your first block begins now![/bold green]")
    console.print("[dim]Press Enter to continue...[/dim]")
    input()
    
    return state
