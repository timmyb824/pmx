"""Tests for the pmx TUI: data shaping and a dashboard smoke test."""

import asyncio
import json

import httpx
from textual.widgets import DataTable, TabbedContent

from pmx.client import ProxmoxClient
from pmx.config import Context
from pmx.tui.app import PmxTuiApp
from pmx.tui.data import fetch_guests, fetch_nodes, fetch_snapshot, fetch_tasks

NODES = [
    {
        "node": "pve2",
        "status": "online",
        "cpu": 0.25,
        "mem": 2**30,
        "maxmem": 2**32,
        "uptime": 90061,
    },
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.05,
        "mem": 2**29,
        "maxmem": 2**32,
        "uptime": 3600,
    },
]

RESOURCES = [
    {
        "type": "qemu",
        "vmid": 102,
        "name": "web",
        "node": "pve1",
        "status": "running",
        "cpu": 0.5,
        "mem": 2**30,
        "maxmem": 2**31,
        "uptime": 7200,
    },
    {"type": "qemu", "vmid": 101, "name": "db", "node": "pve2", "status": "stopped"},
    {
        "type": "lxc",
        "vmid": 200,
        "name": "proxy",
        "node": "pve1",
        "status": "running",
        "cpu": 0.01,
        "mem": 2**28,
        "maxmem": 2**29,
        "uptime": 60,
    },
]

TASKS = [
    {
        "upid": "UPID:pve1:0:0:1:qmstart:101:root@pam:",
        "type": "qmstart",
        "id": "101",
        "node": "pve1",
        "user": "root@pam",
        "starttime": 1700000000,
        "endtime": 1700000005,
        "status": "OK",
    },
    {
        "upid": "UPID:pve1:0:0:2:vzdump:200:root@pam:",
        "type": "vzdump",
        "id": "200",
        "node": "pve1",
        "user": "root@pam",
        "starttime": 1700000100,
    },
]


def _handler(request: httpx.Request) -> httpx.Response:
    """Serve canned cluster data for the mock transport."""
    path = request.url.path
    if path.endswith("/version"):
        return httpx.Response(200, json={"data": {"release": "9.1"}})
    if path.endswith("/nodes"):
        return httpx.Response(200, json={"data": NODES})
    if path.endswith("/cluster/resources"):
        return httpx.Response(200, json={"data": RESOURCES})
    if path.endswith("/cluster/tasks"):
        return httpx.Response(200, json={"data": TASKS})
    return httpx.Response(404, json={"data": None})


def _make_client() -> ProxmoxClient:
    """Build a ProxmoxClient backed by the canned-data mock transport."""
    ctx = Context(
        name="test",
        endpoints=["pve1.lan:8006"],
        user="pmx@pve",
        token_id="tok",
        token_secret="secret",
    )
    return ProxmoxClient(ctx, "s3cr3t", transport=httpx.MockTransport(_handler))


class TestFetchers:
    """Row shaping for each dashboard pane."""

    def test_fetch_nodes_sorted_and_formatted(self) -> None:
        """Nodes are sorted by name with formatted CPU, memory, and uptime."""
        rows = fetch_nodes(_make_client())
        assert [r["node"] for r in rows] == ["pve1", "pve2"]
        assert rows[1]["cpu"] == "25.0%"
        assert rows[1]["mem"] == "1.0 GiB"
        assert rows[1]["uptime"] == "1d 1h 1m"

    def test_fetch_guests_filters_kind_and_sorts_by_vmid(self) -> None:
        """Guests are filtered to the requested kind and sorted by VMID."""
        vms = fetch_guests(_make_client(), "qemu")
        assert [v["vmid"] for v in vms] == [101, 102]
        assert vms[0]["status"] == "stopped"
        assert vms[0]["cpu"] == "-"
        cts = fetch_guests(_make_client(), "lxc")
        assert [c["vmid"] for c in cts] == [200]

    def test_fetch_tasks_newest_first_with_running_fallback(self) -> None:
        """Tasks sort newest-first; unfinished tasks read 'running'."""
        rows = fetch_tasks(_make_client())
        assert rows[0]["type"] == "vzdump"
        assert rows[0]["status"] == "running"
        assert rows[1]["status"] == "OK"

    def test_fetch_snapshot_fills_all_panes(self) -> None:
        """A snapshot carries rows for every pane."""
        snap = fetch_snapshot(_make_client())
        assert len(snap.nodes) == 2
        assert len(snap.vms) == 2
        assert len(snap.cts) == 1
        assert len(snap.tasks) == 2

    def test_rows_are_json_serializable(self) -> None:
        """All pane rows serialize cleanly (display-ready values)."""
        snap = fetch_snapshot(_make_client())
        json.dumps([snap.nodes, snap.vms, snap.cts, snap.tasks])


class TestDashboard:
    """Smoke test for the Textual app against the mock transport."""

    def test_dashboard_populates_tables(self) -> None:
        """The app starts, fetches a snapshot, and fills all four tables."""

        async def run() -> None:
            """Drive the app with the Textual test pilot."""
            app = PmxTuiApp(_make_client(), refresh_interval=3600)
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                assert app.query_one("#table-nodes", DataTable).row_count == 2
                assert app.query_one("#table-vms", DataTable).row_count == 2
                assert app.query_one("#table-cts", DataTable).row_count == 1
                assert app.query_one("#table-tasks", DataTable).row_count == 2

        asyncio.run(run())

    def test_pane_switching_keys(self) -> None:
        """Number keys switch the active pane."""

        async def run() -> None:
            """Drive pane switching with the pilot."""
            app = PmxTuiApp(_make_client(), refresh_interval=3600)
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                await pilot.press("2")
                assert app.query_one(TabbedContent).active == "vms"
                await pilot.press("4")
                assert app.query_one(TabbedContent).active == "tasks"

        asyncio.run(run())
