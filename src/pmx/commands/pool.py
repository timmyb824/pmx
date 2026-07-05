"""Resource pool command group."""

import typer

from pmx.confirm import confirm_action
from pmx.render import console, print_kv, print_table
from pmx.state import app_state, get_client

app = typer.Typer(no_args_is_help=True)

POOL_ARG = typer.Argument(..., help="Pool ID.")


@app.command("ls")
def ls() -> None:
    """List resource pools."""
    with get_client() as client:
        pools = client.get("/pools")
        print_table(
            sorted(pools, key=lambda p: str(p.get("poolid"))),
            [("Pool", "poolid"), ("Comment", "comment")],
            title="Pools",
            as_json=app_state.output_json,
        )


@app.command("info")
def info(poolid: str = POOL_ARG) -> None:
    """Show a pool's members and comment."""
    with get_client() as client:
        data = client.get(f"/pools/{poolid}")
        members = data.get("members", [])
        if app_state.output_json:
            print_kv(data, as_json=True)
            return
        print_kv({"pool": poolid, "comment": data.get("comment", "")}, title=f"Pool — {poolid}")
        print_table(
            members,
            [("Type", "type"), ("ID", "id"), ("Node", "node"), ("Storage", "storage")],
            title="Members",
        )


@app.command("create")
def create(
    poolid: str = POOL_ARG,
    comment: str | None = typer.Option(None, "--comment", help="Pool comment."),
) -> None:
    """Create a resource pool."""
    with get_client() as client:
        client.post("/pools", poolid=poolid, comment=comment)
        console.print(f"[green]done[/] — pool '{poolid}' created")


@app.command("edit")
def edit(
    poolid: str = POOL_ARG,
    comment: str | None = typer.Option(None, "--comment", help="New comment."),
    add_vms: str | None = typer.Option(None, "--add-vms", help="Comma-separated VMIDs to add."),
    remove_vms: str | None = typer.Option(
        None, "--remove-vms", help="Comma-separated VMIDs to remove."
    ),
    add_storage: str | None = typer.Option(
        None, "--add-storage", help="Comma-separated storage IDs to add."
    ),
) -> None:
    """Edit a pool's comment or membership."""
    with get_client() as client:
        if comment is not None:
            client.put(f"/pools/{poolid}", comment=comment)
        if add_vms:
            client.put(f"/pools/{poolid}", vms=add_vms)
        if remove_vms:
            client.put(f"/pools/{poolid}", vms=remove_vms, delete=1)
        if add_storage:
            client.put(f"/pools/{poolid}", storage=add_storage)
        console.print(f"[green]done[/] — pool '{poolid}' updated")


@app.command("remove")
def remove(poolid: str = POOL_ARG) -> None:
    """Remove a resource pool (must be empty)."""
    with get_client() as client:
        confirm_action(f"Remove pool '{poolid}'", app_state.yes)
        client.delete(f"/pools/{poolid}")
        console.print(f"[green]done[/] — pool '{poolid}' removed")
