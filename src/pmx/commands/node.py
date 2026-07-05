"""Node command group: cluster node information."""

import typer

from pmx.pickers import pick_node
from pmx.render import fmt_bytes, fmt_uptime, print_kv, print_table
from pmx.state import app_state, get_client

app = typer.Typer(no_args_is_help=True)


@app.command("ls")
def ls() -> None:
    """List cluster nodes with status and resource usage."""
    with get_client() as client:
        nodes = client.get("/nodes")
        rows = [
            {
                "node": n.get("node"),
                "status": n.get("status"),
                "cpu": f"{float(n.get('cpu', 0)) * 100:.1f}%",
                "mem": fmt_bytes(n.get("mem")),
                "maxmem": fmt_bytes(n.get("maxmem")),
                "uptime": fmt_uptime(n.get("uptime")),
            }
            for n in sorted(nodes, key=lambda n: str(n.get("node")))
        ]
        print_table(
            rows,
            [
                ("Node", "node"), ("Status", "status"), ("CPU", "cpu"),
                ("Memory", "mem"), ("Max Memory", "maxmem"), ("Uptime", "uptime"),
            ],
            title="Nodes",
            as_json=app_state.output_json,
        )


@app.command("info")
def info(
    name: str | None = typer.Argument(None, help="Node name (interactive picker if omitted)."),
) -> None:
    """Show detailed status for a node."""
    with get_client() as client:
        node = name or pick_node(client)
        status = client.get(f"/nodes/{node}/status")
        cpuinfo = status.get("cpuinfo", {})
        memory = status.get("memory", {})
        rootfs = status.get("rootfs", {})
        data = {
            "node": node,
            "pve version": status.get("pveversion"),
            "kernel": status.get("kversion"),
            "uptime": fmt_uptime(status.get("uptime")),
            "load average": ", ".join(str(v) for v in status.get("loadavg", [])),
            "cpu model": cpuinfo.get("model"),
            "cpus": cpuinfo.get("cpus"),
            "memory used": fmt_bytes(memory.get("used")),
            "memory total": fmt_bytes(memory.get("total")),
            "rootfs used": fmt_bytes(rootfs.get("used")),
            "rootfs total": fmt_bytes(rootfs.get("total")),
        }
        print_kv(data, title=f"Node — {node}", as_json=app_state.output_json)
