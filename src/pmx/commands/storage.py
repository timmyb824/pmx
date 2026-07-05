"""Storage command group."""

import typer

from pmx.pickers import pick_node, pick_storage
from pmx.render import console, fmt_bytes, print_kv, print_table
from pmx.state import app_state, get_client

app = typer.Typer(no_args_is_help=True)

STORAGE_ARG = typer.Argument(None, help="Storage ID (interactive picker if omitted).")


@app.command("ls")
def ls() -> None:
    """List storages with cluster-wide usage."""
    with get_client() as client:
        resources = client.get("/cluster/resources", type="storage")
        seen: dict[str, dict] = {}
        for res in resources:
            sid = str(res.get("storage"))
            row = seen.setdefault(
                sid,
                {
                    "storage": sid,
                    "type": res.get("plugintype"),
                    "status": res.get("status"),
                    "used": fmt_bytes(res.get("disk")),
                    "total": fmt_bytes(res.get("maxdisk")),
                    "nodes": set(),
                },
            )
            row["nodes"].add(str(res.get("node")))
        rows = [
            {**row, "nodes": ", ".join(sorted(row["nodes"]))}
            for row in sorted(seen.values(), key=lambda r: str(r["storage"]))
        ]
        print_table(
            rows,
            [
                ("Storage", "storage"), ("Type", "type"), ("Status", "status"),
                ("Used", "used"), ("Total", "total"), ("Nodes", "nodes"),
            ],
            title="Storages",
            as_json=app_state.output_json,
        )


@app.command("info")
def info(storage: str | None = STORAGE_ARG) -> None:
    """Show a storage's configuration."""
    with get_client() as client:
        sid = storage or pick_storage(client)
        data = client.get(f"/storage/{sid}")
        print_kv(data, title=f"Storage — {sid}", as_json=app_state.output_json)


@app.command("content")
def content(
    storage: str | None = STORAGE_ARG,
    node: str | None = typer.Option(None, "--node", help="Node to query (picker if omitted)."),
    content_type: str | None = typer.Option(
        None, "--type", help="Filter by content type (e.g. iso, backup, images)."
    ),
) -> None:
    """List the contents of a storage on a node."""
    with get_client() as client:
        sid = storage or pick_storage(client)
        target = node or pick_node(client, "Select node to query")
        items = client.get(f"/nodes/{target}/storage/{sid}/content", content=content_type)
        rows = [
            {
                "volid": i.get("volid"),
                "content": i.get("content"),
                "format": i.get("format"),
                "size": fmt_bytes(i.get("size")),
                "vmid": i.get("vmid"),
            }
            for i in sorted(items, key=lambda i: str(i.get("volid")))
        ]
        print_table(
            rows,
            [
                ("Volume", "volid"), ("Content", "content"), ("Format", "format"),
                ("Size", "size"), ("VMID", "vmid"),
            ],
            title=f"Content — {sid} on {target}",
            as_json=app_state.output_json,
        )


def _set_enabled(storage: str | None, enabled: bool) -> None:
    """Enable or disable a storage cluster-wide."""
    with get_client() as client:
        sid = storage or pick_storage(client)
        client.put(f"/storage/{sid}", disable=0 if enabled else 1)
        state = "enabled" if enabled else "disabled"
        console.print(f"[green]done[/] — storage '{sid}' {state}")


@app.command("enable")
def enable(storage: str | None = STORAGE_ARG) -> None:
    """Enable a storage."""
    _set_enabled(storage, True)


@app.command("disable")
def disable(storage: str | None = STORAGE_ARG) -> None:
    """Disable a storage."""
    _set_enabled(storage, False)
