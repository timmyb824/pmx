"""Proxmox task (UPID) handling: parsing, waiting, and log retrieval."""

import time
from dataclasses import dataclass

from rich.console import Console

from pmx.client import PMXError, ProxmoxClient

POLL_INTERVAL = 1.0


@dataclass
class Upid:
    """A parsed Proxmox task identifier."""

    raw: str
    node: str
    task_type: str
    task_id: str
    user: str

    @classmethod
    def parse(cls, raw: str) -> "Upid":
        """Parse a UPID string (UPID:node:pid:pstart:starttime:type:id:user:...)."""
        parts = raw.split(":")
        if len(parts) < 8 or parts[0] != "UPID":
            raise PMXError(f"invalid UPID: {raw!r}")
        return cls(raw=raw, node=parts[1], task_type=parts[5], task_id=parts[6], user=parts[7])


def task_status(client: ProxmoxClient, upid: Upid) -> dict:
    """Return the current status object for a task."""
    return client.get(f"/nodes/{upid.node}/tasks/{upid.raw}/status")


def task_log(client: ProxmoxClient, upid: Upid, start: int = 0, limit: int = 500) -> list[dict]:
    """Return log lines for a task."""
    return client.get(f"/nodes/{upid.node}/tasks/{upid.raw}/log", start=start, limit=limit)


def wait_for_task(
    client: ProxmoxClient,
    raw_upid: str,
    console: Console,
    description: str = "working",
    poll_interval: float = POLL_INTERVAL,
) -> None:
    """Block until a task finishes, showing a spinner; raise PMXError on failure."""
    upid = Upid.parse(raw_upid)
    with console.status(f"[bold cyan]{description}[/] ({upid.task_type} on {upid.node})"):
        while True:
            status = task_status(client, upid)
            if status.get("status") != "running":
                break
            time.sleep(poll_interval)
    exitstatus = str(status.get("exitstatus", ""))
    if exitstatus != "OK":
        raise PMXError(f"task {upid.raw} failed: {exitstatus}")


def run_and_wait(
    client: ProxmoxClient,
    raw_upid: str | None,
    console: Console,
    description: str,
    no_wait: bool,
) -> None:
    """Handle a task-returning API call result: wait by default or print the UPID."""
    if not raw_upid or not str(raw_upid).startswith("UPID"):
        console.print(f"[green]done[/] — {description}")
        return
    if no_wait:
        console.print(str(raw_upid))
        return
    wait_for_task(client, str(raw_upid), console, description)
    console.print(f"[green]done[/] — {description}")
