"""Tests for pmx.tasks UPID parsing and task waiting."""

import httpx
import pytest
from rich.console import Console

from pmx.client import PMXError, ProxmoxClient
from pmx.config import Context
from pmx.tasks import Upid, wait_for_task

UPID_RAW = "UPID:pve1:0001C0FA:0A3F1234:65ABCDEF:qmstart:101:root@pam!tok:"


class TestUpidParse:
    """UPID string parsing."""

    def test_parse_valid(self) -> None:
        """A valid UPID parses into its fields."""
        upid = Upid.parse(UPID_RAW)
        assert upid.node == "pve1"
        assert upid.task_type == "qmstart"
        assert upid.task_id == "101"
        assert upid.user == "root@pam!tok"

    def test_parse_invalid_raises(self) -> None:
        """Garbage input raises PMXError."""
        with pytest.raises(PMXError):
            Upid.parse("not-a-upid")


class TestWaitForTask:
    """Task polling behavior."""

    @staticmethod
    def _client(statuses: list[dict]) -> ProxmoxClient:
        """Build a client whose task status endpoint returns queued responses."""
        queue = list(statuses)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/status") and "/tasks/" in request.url.path:
                return httpx.Response(200, json={"data": queue.pop(0)})
            return httpx.Response(200, json={"data": {}})

        ctx = Context(name="t", endpoints=["pve1.lan:8006"], user="u@p", token_id="t")
        return ProxmoxClient(ctx, "s", transport=httpx.MockTransport(handler))

    def test_success(self) -> None:
        """A task that ends with exitstatus OK completes silently."""
        client = self._client([{"status": "running"}, {"status": "stopped", "exitstatus": "OK"}])
        wait_for_task(client, UPID_RAW, Console(quiet=True), poll_interval=0)

    def test_failure_raises(self) -> None:
        """A failed task raises PMXError with the exit status."""
        client = self._client([{"status": "stopped", "exitstatus": "some error"}])
        with pytest.raises(PMXError, match="some error"):
            wait_for_task(client, UPID_RAW, Console(quiet=True), poll_interval=0)
