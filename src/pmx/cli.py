"""pmx CLI entry point: root Typer app, global flags, and error handling."""

import typer

from pmx import __version__
from pmx.client import PMXError
from pmx.commands import backup, context, ct, node, pool, setup, storage, task, vm
from pmx.config import ConfigError
from pmx.render import err_console
from pmx.state import app_state
from pmx.tui.app import run_tui

app = typer.Typer(
    name="pmx",
    help="Manage a Proxmox VE cluster from your terminal — no SSH, no web UI.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

app.add_typer(context.app, name="context", help="Manage connection contexts.")
app.add_typer(node.app, name="node", help="Cluster node information.")
app.add_typer(vm.app, name="vm", help="Manage virtual machines (QEMU).")
app.add_typer(ct.app, name="ct", help="Manage containers (LXC).")
app.add_typer(backup.app, name="backup", help="Manage backups.")
app.add_typer(storage.app, name="storage", help="Manage storages.")
app.add_typer(pool.app, name="pool", help="Manage resource pools.")
app.add_typer(task.app, name="task", help="Monitor cluster tasks.")
app.command(name="setup", help="Interactive first-run configuration.")(setup.run_setup)


@app.command("tui")
def tui() -> None:
    """Launch the interactive k9s-style dashboard."""
    run_tui()


def _version_callback(value: bool) -> None:
    """Print the version and exit when --version is passed."""
    if value:
        typer.echo(f"pmx {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    context_name: str | None = typer.Option(
        None, "--context", "-c", help="Context to use (overrides the default)."
    ),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts."),
    no_wait: bool = typer.Option(
        False, "--no-wait", help="Do not wait for tasks; print the UPID and return."
    ),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Collect global flags into shared state before dispatching to subcommands."""
    app_state.context_name = context_name
    app_state.output_json = output == "json"
    app_state.yes = yes
    app_state.no_wait = no_wait


def run() -> None:
    """Run the CLI, translating pmx errors into clean exit codes."""
    try:
        app()
    except (PMXError, ConfigError) as exc:
        err_console.print(f"[bold red]error:[/] {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    run()
