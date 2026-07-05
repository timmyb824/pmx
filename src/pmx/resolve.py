"""Resolve guests (VMs/containers) to their node and metadata via cluster resources."""

from dataclasses import dataclass

from pmx.client import PMXError, ProxmoxClient


@dataclass
class Guest:
    """A VM or container located in the cluster."""

    vmid: int
    name: str
    node: str
    kind: str
    status: str

    @property
    def base_path(self) -> str:
        """Return the API base path for this guest (e.g. /nodes/pve1/qemu/101)."""
        return f"/nodes/{self.node}/{self.kind}/{self.vmid}"

    @property
    def label(self) -> str:
        """Return a human-readable label for confirmations and messages."""
        noun = "VM" if self.kind == "qemu" else "CT"
        return f"{noun} {self.vmid} ({self.name})"


def list_guests(client: ProxmoxClient, kind: str) -> list[Guest]:
    """List all guests of a kind ('qemu' or 'lxc') across the cluster."""
    resources = client.get("/cluster/resources", type="vm")
    guests = [
        Guest(
            vmid=int(res["vmid"]),
            name=str(res.get("name", "")),
            node=str(res["node"]),
            kind=str(res["type"]),
            status=str(res.get("status", "unknown")),
        )
        for res in resources
        if res.get("type") == kind
    ]
    return sorted(guests, key=lambda g: g.vmid)


def resolve_guest(client: ProxmoxClient, kind: str, vmid: int) -> Guest:
    """Find a guest by VMID, raising PMXError if it does not exist."""
    for guest in list_guests(client, kind):
        if guest.vmid == vmid:
            return guest
    noun = "VM" if kind == "qemu" else "container"
    raise PMXError(f"{noun} {vmid} not found in the cluster")
