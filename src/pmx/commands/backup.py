"""Backup command group: list, restore, and delete vzdump backups."""

import typer
from InquirerPy import inquirer

from pmx.client import PMXError, ProxmoxClient
from pmx.confirm import confirm_action
from pmx.render import console, fmt_bytes, print_table
from pmx.state import app_state, get_client
from pmx.tasks import run_and_wait

app = typer.Typer(no_args_is_help=True)


def _list_backups(client: ProxmoxClient, storage: str | None, vmid: int | None) -> list[dict]:
    """Collect backup volumes across all nodes and backup-capable storages."""
    backups: list[dict] = []
    seen: set[str] = set()
    for node in client.get("/nodes"):
        if node.get("status") != "online":
            continue
        node_name = str(node["node"])
        for store in client.get(f"/nodes/{node_name}/storage", content="backup"):
            sid = str(store["storage"])
            if storage and sid != storage:
                continue
            key = f"{sid}"
            if key in seen and store.get("shared"):
                continue
            if store.get("shared"):
                seen.add(key)
            items = client.get(
                f"/nodes/{node_name}/storage/{sid}/content", content="backup", vmid=vmid
            )
            for item in items:
                backups.append({**item, "node": node_name, "storage": sid})
    return sorted(backups, key=lambda b: (b.get("vmid") or 0, b.get("ctime") or 0))


def _pick_backup(backups: list[dict], message: str) -> dict:
    """Fuzzy-pick a backup volume."""
    if not backups:
        raise PMXError("no backups found")
    choices = [
        {
            "name": f"{b.get('vmid', '-'):<6} {str(b.get('volid', '')):<70} {fmt_bytes(b.get('size'))}",
            "value": b,
        }
        for b in backups
    ]
    result = inquirer.fuzzy(message=message, choices=choices).execute()
    if result is None:
        raise PMXError("selection cancelled")
    return result


@app.command("ls")
def ls(
    storage: str | None = typer.Option(None, "--storage", "-s", help="Filter by storage."),
    vmid: int | None = typer.Option(None, "--vmid", help="Filter by VMID."),
) -> None:
    """List backups across the cluster."""
    with get_client() as client:
        rows = [
            {
                "volid": b.get("volid"),
                "vmid": b.get("vmid"),
                "storage": b.get("storage"),
                "format": b.get("format"),
                "size": fmt_bytes(b.get("size")),
                "notes": b.get("notes"),
            }
            for b in _list_backups(client, storage, vmid)
        ]
        print_table(
            rows,
            [
                ("Volume", "volid"),
                ("VMID", "vmid"),
                ("Storage", "storage"),
                ("Format", "format"),
                ("Size", "size"),
                ("Notes", "notes"),
            ],
            title="Backups",
            as_json=app_state.output_json,
        )


@app.command("restore")
def restore(
    volid: str | None = typer.Argument(None, help="Backup volume ID (picker if omitted)."),
    vmid: int | None = typer.Option(None, "--vmid", help="Target VMID (default: next free)."),
    node: str | None = typer.Option(None, "--node", help="Target node."),
    storage: str | None = typer.Option(None, "--storage", help="Target storage for disks."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing guest."),
) -> None:
    """Restore a VM or container from a backup."""
    with get_client() as client:
        if volid is None:
            backup = _pick_backup(_list_backups(client, None, None), "Select backup to restore")
            volid = str(backup["volid"])
            node = node or str(backup["node"])
        if node is None:
            raise PMXError("--node is required when passing a volume ID directly")
        target_vmid = vmid or int(client.get("/cluster/nextid"))
        is_lxc = "lxc" in volid or "/ct/" in volid
        confirm_action(f"Restore {volid} to VMID {target_vmid} on {node}", app_state.yes)
        if is_lxc:
            upid = client.post(
                f"/nodes/{node}/lxc",
                vmid=target_vmid,
                ostemplate=volid,
                restore=1,
                storage=storage,
                force=1 if force else None,
            )
        else:
            upid = client.post(
                f"/nodes/{node}/qemu",
                vmid=target_vmid,
                archive=volid,
                storage=storage,
                force=1 if force else None,
            )
        run_and_wait(client, upid, console, f"restore {volid} -> {target_vmid}", app_state.no_wait)


@app.command("delete")
def delete(
    volid: str | None = typer.Argument(None, help="Backup volume ID (picker if omitted)."),
    node: str | None = typer.Option(None, "--node", help="Node that can access the storage."),
) -> None:
    """Delete a backup volume."""
    with get_client() as client:
        if volid is None:
            backup = _pick_backup(_list_backups(client, None, None), "Select backup to delete")
            volid = str(backup["volid"])
            node = node or str(backup["node"])
        if node is None:
            raise PMXError("--node is required when passing a volume ID directly")
        storage_id = volid.split(":", 1)[0]
        confirm_action(f"Delete backup {volid}", app_state.yes)
        upid = client.delete(f"/nodes/{node}/storage/{storage_id}/content/{volid}")
        run_and_wait(client, upid, console, f"delete {volid}", app_state.no_wait)
