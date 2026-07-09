"""Confirmation prompts for destructive operations."""

import typer
from rich.console import Console

console = Console()


def confirm_action(message: str, yes: bool) -> None:
    """Prompt for a yes/no confirmation unless --yes was given; abort on decline."""
    if yes:
        return
    if not typer.confirm(f"{message}?"):
        raise typer.Abort()


def confirm_destroy(label: str, expected: str, yes: bool) -> None:
    """Require typing the guest name or ID to confirm destruction (skipped by --yes)."""
    if yes:
        return
    console.print(
        f"[bold red]This will permanently destroy {label}.[/] Type its name or ID to confirm."
    )
    answer = typer.prompt("Confirm").strip()
    parts = {p.strip() for p in expected.split("|")}
    if answer not in parts:
        console.print("[red]confirmation did not match — aborting[/]")
        raise typer.Abort()
