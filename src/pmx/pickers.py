"""Interactive fuzzy pickers used when command arguments are omitted."""

from InquirerPy import inquirer

from pmx.client import PMXError, ProxmoxClient
from pmx.resolve import Guest, list_guests


def _fuzzy_select(message: str, choices: list[dict]) -> object:
    """Run a fuzzy prompt and return the selected value, raising PMXError on cancel."""
    if not choices:
        raise PMXError("nothing to select")
    result = inquirer.fuzzy(message=message, choices=choices).execute()
    if result is None:
        raise PMXError("selection cancelled")
    return result


def pick_guest(client: ProxmoxClient, kind: str, message: str = "Select") -> Guest:
    """Fuzzy-pick a guest, showing ID, name, node, and status for each row."""
    guests = list_guests(client, kind)
    choices = [
        {
            "name": f"{g.vmid:<6} {g.name:<24} {g.node:<12} {g.status}",
            "value": g,
        }
        for g in guests
    ]
    return _fuzzy_select(message, choices)  # type: ignore[return-value]


def pick_node(client: ProxmoxClient, message: str = "Select node") -> str:
    """Fuzzy-pick a cluster node by name."""
    nodes = client.get("/nodes")
    choices = [
        {
            "name": f"{n['node']:<16} {n.get('status', 'unknown')}",
            "value": str(n["node"]),
        }
        for n in sorted(nodes, key=lambda n: str(n["node"]))
    ]
    return str(_fuzzy_select(message, choices))


def pick_storage(client: ProxmoxClient, message: str = "Select storage") -> str:
    """Fuzzy-pick a storage by ID."""
    storages = client.get("/storage")
    choices = [
        {
            "name": f"{s['storage']:<20} {s.get('type', '')}",
            "value": str(s["storage"]),
        }
        for s in sorted(storages, key=lambda s: str(s["storage"]))
    ]
    return str(_fuzzy_select(message, choices))


def pick_snapshot(client: ProxmoxClient, guest: Guest, message: str = "Select snapshot") -> str:
    """Fuzzy-pick a snapshot name for a guest (excluding the 'current' pseudo-snapshot)."""
    snapshots = client.get(f"{guest.base_path}/snapshot")
    choices = [
        {
            "name": f"{s['name']:<24} {s.get('description', '')}",
            "value": str(s["name"]),
        }
        for s in snapshots
        if s.get("name") != "current"
    ]
    return str(_fuzzy_select(message, choices))
