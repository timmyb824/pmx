"""Factory building the shared vm/ct command groups (lifecycle, snapshots, ops)."""

from collections.abc import Callable

import typer

from pmx.client import ProxmoxClient
from pmx.confirm import confirm_action, confirm_destroy
from pmx.pickers import pick_guest, pick_node, pick_snapshot, pick_storage
from pmx.render import console, fmt_bytes, fmt_uptime, print_kv, print_table
from pmx.resolve import Guest, list_guests, resolve_guest
from pmx.state import app_state, get_client
from pmx.tasks import run_and_wait

VMID_ARG = typer.Argument(None, help="Guest VMID (interactive picker if omitted).")


def _get_guest(client: ProxmoxClient, kind: str, vmid: int | None, action: str) -> Guest:
    """Resolve a guest by VMID or fall back to an interactive picker."""
    noun = "VM" if kind == "qemu" else "container"
    if vmid is None:
        return pick_guest(client, kind, message=f"Select {noun} to {action}")
    return resolve_guest(client, kind, vmid)


def _simple_status_command(kind: str, action: str, description: str) -> Callable[..., None]:
    """Build a command that POSTs to a guest's status endpoint and waits for the task."""

    def command(vmid: int | None = VMID_ARG) -> None:
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, action)
            upid = client.post(f"{guest.base_path}/status/{action}")
            run_and_wait(client, upid, console, f"{action} {guest.label}", app_state.no_wait)

    command.__doc__ = description
    return command


def _build_snapshot_app(kind: str) -> typer.Typer:
    """Build the snapshot sub-app for a guest kind."""
    snap = typer.Typer(no_args_is_help=True)

    @snap.command("ls")
    def snap_ls(vmid: int | None = VMID_ARG) -> None:
        """List snapshots for a guest."""
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, "list snapshots for")
            snapshots = client.get(f"{guest.base_path}/snapshot")
            print_table(
                sorted(snapshots, key=lambda s: s.get("snaptime", 0)),
                [
                    ("Name", "name"),
                    ("Description", "description"),
                    ("Parent", "parent"),
                ],
                title=f"Snapshots — {guest.label}",
                as_json=app_state.output_json,
            )

    @snap.command("create")
    def snap_create(
        vmid: int | None = VMID_ARG,
        name: str = typer.Option(..., "--name", "-n", help="Snapshot name."),
        description: str = typer.Option("", "--description", "-d", help="Snapshot description."),
    ) -> None:
        """Create a snapshot."""
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, "snapshot")
            upid = client.post(
                f"{guest.base_path}/snapshot",
                snapname=name,
                description=description or None,
            )
            run_and_wait(
                client,
                upid,
                console,
                f"snapshot {name} of {guest.label}",
                app_state.no_wait,
            )

    @snap.command("delete")
    def snap_delete(
        vmid: int | None = VMID_ARG,
        name: str | None = typer.Option(None, "--name", "-n", help="Snapshot name."),
    ) -> None:
        """Delete a snapshot."""
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, "delete a snapshot from")
            snapname = name or pick_snapshot(client, guest, "Select snapshot to delete")
            confirm_action(f"Delete snapshot '{snapname}' of {guest.label}", app_state.yes)
            upid = client.delete(f"{guest.base_path}/snapshot/{snapname}")
            run_and_wait(client, upid, console, f"delete snapshot {snapname}", app_state.no_wait)

    @snap.command("rollback")
    def snap_rollback(
        vmid: int | None = VMID_ARG,
        name: str | None = typer.Option(None, "--name", "-n", help="Snapshot name."),
    ) -> None:
        """Roll a guest back to a snapshot."""
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, "roll back")
            snapname = name or pick_snapshot(client, guest, "Select snapshot to roll back to")
            confirm_action(
                f"Roll back {guest.label} to snapshot '{snapname}' (current state is lost)",
                app_state.yes,
            )
            upid = client.post(f"{guest.base_path}/snapshot/{snapname}/rollback")
            run_and_wait(client, upid, console, f"rollback to {snapname}", app_state.no_wait)

    return snap


def build_guest_app(kind: str) -> typer.Typer:
    """Build the full command group for a guest kind ('qemu' or 'lxc')."""
    noun = "VM" if kind == "qemu" else "container"
    app = typer.Typer(no_args_is_help=True)
    app.add_typer(_build_snapshot_app(kind), name="snapshot", help=f"Manage {noun} snapshots.")

    @app.command("ls")
    def ls() -> None:
        """List guests across the cluster."""
        with get_client() as client:
            rows = [
                {"vmid": g.vmid, "name": g.name, "node": g.node, "status": g.status}
                for g in list_guests(client, kind)
            ]
            print_table(
                rows,
                [
                    ("VMID", "vmid"),
                    ("Name", "name"),
                    ("Node", "node"),
                    ("Status", "status"),
                ],
                title=f"{noun}s",
                as_json=app_state.output_json,
            )

    @app.command("info")
    def info(vmid: int | None = VMID_ARG) -> None:
        """Show current status details for a guest."""
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, "inspect")
            status = client.get(f"{guest.base_path}/status/current")
            data = {
                "vmid": guest.vmid,
                "name": guest.name,
                "node": guest.node,
                "status": status.get("status"),
                "uptime": fmt_uptime(status.get("uptime")),
                "cpus": status.get("cpus"),
                "memory": fmt_bytes(status.get("mem")),
                "max memory": fmt_bytes(status.get("maxmem")),
                "disk": fmt_bytes(status.get("disk")),
                "max disk": fmt_bytes(status.get("maxdisk")),
            }
            print_kv(data, title=guest.label, as_json=app_state.output_json)

    @app.command("config")
    def config(vmid: int | None = VMID_ARG) -> None:
        """Show a guest's configuration."""
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, "inspect")
            cfg = client.get(f"{guest.base_path}/config")
            print_kv(cfg, title=f"Config — {guest.label}", as_json=app_state.output_json)

    app.command("start")(_simple_status_command(kind, "start", f"Start a {noun}."))
    app.command("stop")(_simple_status_command(kind, "stop", f"Hard-stop a {noun}."))
    app.command("shutdown")(
        _simple_status_command(kind, "shutdown", f"Gracefully shut down a {noun}.")
    )
    app.command("reboot")(_simple_status_command(kind, "reboot", f"Reboot a {noun}."))
    if kind == "qemu":
        app.command("reset")(_simple_status_command(kind, "reset", "Hard-reset a VM."))
        app.command("suspend")(_simple_status_command(kind, "suspend", "Suspend a VM."))
        app.command("resume")(_simple_status_command(kind, "resume", "Resume a suspended VM."))

    @app.command("rename")
    def rename(
        vmid: int | None = VMID_ARG,
        name: str = typer.Option(..., "--name", "-n", help="New name."),
    ) -> None:
        """Rename a guest."""
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, "rename")
            key = "name" if kind == "qemu" else "hostname"
            client.put(f"{guest.base_path}/config", **{key: name})
            console.print(f"[green]done[/] — renamed {guest.label} to '{name}'")

    @app.command("destroy")
    def destroy(
        vmid: int | None = VMID_ARG,
        purge: bool = typer.Option(
            False, "--purge", help="Also remove from backup jobs, HA, and replication."
        ),
    ) -> None:
        """Permanently destroy a guest and its disks."""
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, "destroy")
            confirm_destroy(guest.label, f"{guest.vmid}|{guest.name}", app_state.yes)
            upid = client.delete(guest.base_path, purge=1 if purge else None)
            run_and_wait(client, upid, console, f"destroy {guest.label}", app_state.no_wait)

    @app.command("clone")
    def clone(
        vmid: int | None = VMID_ARG,
        newid: int | None = typer.Option(
            None, "--newid", help="VMID for the clone (default: next free)."
        ),
        name: str | None = typer.Option(None, "--name", "-n", help="Name for the clone."),
        target: str | None = typer.Option(None, "--target", help="Target node for the clone."),
        full: bool = typer.Option(False, "--full", help="Full clone instead of linked clone."),
        storage: str | None = typer.Option(None, "--storage", help="Target storage (full clone)."),
    ) -> None:
        """Clone a guest."""
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, "clone")
            new_vmid = newid or int(client.get("/cluster/nextid"))
            name_key = "name" if kind == "qemu" else "hostname"
            params = {
                "newid": new_vmid,
                name_key: name,
                "target": target,
                "full": 1 if full else None,
                "storage": storage,
            }
            upid = client.post(f"{guest.base_path}/clone", **params)
            run_and_wait(
                client,
                upid,
                console,
                f"clone {guest.label} -> {new_vmid}",
                app_state.no_wait,
            )

    @app.command("migrate")
    def migrate(
        vmid: int | None = VMID_ARG,
        target: str | None = typer.Option(None, "--target", help="Target node."),
        online: bool = typer.Option(False, "--online", help="Live migration (running guests)."),
    ) -> None:
        """Migrate a guest to another node."""
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, "migrate")
            dest = target or pick_node(client, "Select target node")
            confirm_action(f"Migrate {guest.label} from {guest.node} to {dest}", app_state.yes)
            online_key = "online" if kind == "qemu" else "restart"
            params = {"target": dest, online_key: 1 if online else None}
            upid = client.post(f"{guest.base_path}/migrate", **params)
            run_and_wait(
                client,
                upid,
                console,
                f"migrate {guest.label} -> {dest}",
                app_state.no_wait,
            )

    @app.command("backup")
    def backup(
        vmid: int | None = VMID_ARG,
        storage: str | None = typer.Option(None, "--storage", "-s", help="Target backup storage."),
        mode: str = typer.Option(
            "snapshot", "--mode", help="Backup mode: snapshot, suspend, or stop."
        ),
        notes: str | None = typer.Option(None, "--notes", help="Backup notes."),
    ) -> None:
        """Back up a guest with vzdump."""
        with get_client() as client:
            guest = _get_guest(client, kind, vmid, "back up")
            store = storage or pick_storage(client, "Select backup storage")
            upid = client.post(
                f"/nodes/{guest.node}/vzdump",
                vmid=guest.vmid,
                storage=store,
                mode=mode,
                **({"notes-template": notes} if notes else {}),
            )
            run_and_wait(client, upid, console, f"backup {guest.label}", app_state.no_wait)

    return app
