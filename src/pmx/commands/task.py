"""Task command group: list, inspect, tail, and wait on cluster tasks."""

from datetime import datetime

import typer

from pmx.render import console, print_kv, print_table
from pmx.state import app_state, get_client
from pmx.tasks import Upid, task_log, task_status, wait_for_task

app = typer.Typer(no_args_is_help=True)

UPID_ARG = typer.Argument(..., help="Task UPID.")


def _fmt_time(value: object) -> str:
    """Format a unix timestamp for display."""
    if not isinstance(value, (int, float)):
        return "-"
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


@app.command("ls")
def ls(
    running: bool = typer.Option(False, "--running", help="Show only running tasks."),
    limit: int = typer.Option(25, "--limit", "-l", help="Maximum tasks to show."),
) -> None:
    """List recent cluster tasks."""
    with get_client() as client:
        tasks = client.get("/cluster/tasks")
        if running:
            tasks = [t for t in tasks if not t.get("endtime")]
        tasks = sorted(tasks, key=lambda t: t.get("starttime", 0), reverse=True)[:limit]
        rows = [
            {
                "upid": t.get("upid"),
                "type": t.get("type"),
                "id": t.get("id"),
                "node": t.get("node"),
                "user": t.get("user"),
                "started": _fmt_time(t.get("starttime")),
                "status": t.get("status") or ("running" if not t.get("endtime") else "-"),
            }
            for t in tasks
        ]
        print_table(
            rows,
            [
                ("UPID", "upid"),
                ("Type", "type"),
                ("ID", "id"),
                ("Node", "node"),
                ("User", "user"),
                ("Started", "started"),
                ("Status", "status"),
            ],
            title="Tasks",
            as_json=app_state.output_json,
        )


@app.command("status")
def status(upid: str = UPID_ARG) -> None:
    """Show the status of a task."""
    with get_client() as client:
        data = task_status(client, Upid.parse(upid))
        print_kv(data, title="Task status", as_json=app_state.output_json)


@app.command("log")
def log(
    upid: str = UPID_ARG,
    limit: int = typer.Option(500, "--limit", "-l", help="Maximum log lines."),
) -> None:
    """Print the log of a task."""
    with get_client() as client:
        lines = task_log(client, Upid.parse(upid), limit=limit)
        for line in lines:
            console.print(line.get("t", ""))


@app.command("wait")
def wait(upid: str = UPID_ARG) -> None:
    """Block until a task finishes; exit non-zero if it failed."""
    with get_client() as client:
        wait_for_task(client, upid, console, "waiting for task")
        console.print("[green]done[/] — task completed successfully")
