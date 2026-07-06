"""Data fetching and row shaping for the pmx TUI dashboard.

Each fetch function returns a list of plain dicts whose values are
display-ready strings, plus the raw fields needed to drive actions
(vmid, node, status).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pmx.client import ProxmoxClient
from pmx.render import fmt_bytes, fmt_uptime

TASK_LIMIT = 50

NODE_COLUMNS: list[tuple[str, str]] = [
    ("Node", "node"),
    ("Status", "status"),
    ("CPU", "cpu"),
    ("Memory", "mem"),
    ("Max Memory", "maxmem"),
    ("Uptime", "uptime"),
]

GUEST_COLUMNS: list[tuple[str, str]] = [
    ("ID", "vmid"),
    ("Name", "name"),
    ("Node", "node"),
    ("Status", "status"),
    ("CPU", "cpu"),
    ("Memory", "mem"),
    ("Max Memory", "maxmem"),
    ("Uptime", "uptime"),
]

TASK_COLUMNS: list[tuple[str, str]] = [
    ("Type", "type"),
    ("ID", "id"),
    ("Node", "node"),
    ("User", "user"),
    ("Started", "started"),
    ("Status", "status"),
]


def fmt_time(value: Any) -> str:
    """Format a unix timestamp as 'YYYY-MM-DD HH:MM:SS'."""
    if not isinstance(value, (int, float)):
        return "-"
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def fmt_cpu(value: Any) -> str:
    """Format a CPU usage fraction as a percentage."""
    if not isinstance(value, (int, float)):
        return "-"
    return f"{float(value) * 100:.1f}%"


def fetch_nodes(client: ProxmoxClient) -> list[dict]:
    """Fetch cluster nodes as display-ready rows."""
    nodes = client.get("/nodes") or []
    return [
        {
            "node": str(n.get("node", "")),
            "status": str(n.get("status", "unknown")),
            "cpu": fmt_cpu(n.get("cpu")),
            "mem": fmt_bytes(n.get("mem")),
            "maxmem": fmt_bytes(n.get("maxmem")),
            "uptime": fmt_uptime(n.get("uptime")),
        }
        for n in sorted(nodes, key=lambda n: str(n.get("node")))
    ]


def fetch_guests(client: ProxmoxClient, kind: str) -> list[dict]:
    """Fetch guests of a kind ('qemu' or 'lxc') as display-ready rows."""
    resources = client.get("/cluster/resources", type="vm") or []
    guests = [
        {
            "vmid": int(res["vmid"]),
            "name": str(res.get("name", "")),
            "node": str(res.get("node", "")),
            "status": str(res.get("status", "unknown")),
            "cpu": fmt_cpu(res.get("cpu")),
            "mem": fmt_bytes(res.get("mem")),
            "maxmem": fmt_bytes(res.get("maxmem")),
            "uptime": fmt_uptime(res.get("uptime")),
        }
        for res in resources
        if res.get("type") == kind
    ]
    return sorted(guests, key=lambda g: g["vmid"])


def fetch_tasks(client: ProxmoxClient, limit: int = TASK_LIMIT) -> list[dict]:
    """Fetch recent cluster tasks as display-ready rows, newest first."""
    tasks = client.get("/cluster/tasks") or []
    tasks = sorted(tasks, key=lambda t: t.get("starttime", 0), reverse=True)[:limit]
    return [
        {
            "type": str(t.get("type", "")),
            "id": str(t.get("id") or "-"),
            "node": str(t.get("node", "")),
            "user": str(t.get("user", "")),
            "started": fmt_time(t.get("starttime")),
            "status": str(t.get("status") or ("running" if not t.get("endtime") else "-")),
        }
        for t in tasks
    ]


@dataclass
class Snapshot:
    """A point-in-time view of the cluster for the dashboard."""

    nodes: list[dict] = field(default_factory=list)
    vms: list[dict] = field(default_factory=list)
    cts: list[dict] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)


def fetch_snapshot(client: ProxmoxClient) -> Snapshot:
    """Fetch all dashboard panes in one pass."""
    return Snapshot(
        nodes=fetch_nodes(client),
        vms=fetch_guests(client, "qemu"),
        cts=fetch_guests(client, "lxc"),
        tasks=fetch_tasks(client),
    )
