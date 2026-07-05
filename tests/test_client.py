"""Tests for pmx.client using httpx.MockTransport."""

import httpx
import pytest

from pmx.client import PMXError, ProxmoxClient, split_endpoint
from pmx.config import Context


def _make_context() -> Context:
    """Build a test context."""
    return Context(
        name="test",
        endpoints=["pve1.lan:8006"],
        user="pmx@pve",
        token_id="tok",
        token_secret="secret",
    )


def _client_with_handler(handler) -> ProxmoxClient:
    """Build a ProxmoxClient backed by a MockTransport."""
    return ProxmoxClient(
        _make_context(), "s3cr3t", transport=httpx.MockTransport(handler)
    )


class TestSplitEndpoint:
    """Endpoint string parsing."""

    def test_with_port(self) -> None:
        """host:port splits correctly."""
        assert split_endpoint("pve1.lan:9000") == ("pve1.lan", 9000)

    def test_without_port_defaults_to_8006(self) -> None:
        """A bare host defaults to port 8006."""
        assert split_endpoint("10.0.0.5") == ("10.0.0.5", 8006)


class TestProxmoxClient:
    """Request behavior, auth, and error handling."""

    def test_auth_header_and_data_unwrap(self) -> None:
        """Requests carry the PVEAPIToken header and responses unwrap 'data'."""
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"data": {"release": "9.1"}})

        client = _client_with_handler(handler)
        result = client.get("/version")
        assert result == {"release": "9.1"}
        assert seen["auth"] == "PVEAPIToken=pmx@pve!tok=s3cr3t"

    def test_api_error_raises_pmxerror_with_message(self) -> None:
        """HTTP errors surface the API's message/errors fields."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/version"):
                return httpx.Response(200, json={"data": {}})
            return httpx.Response(
                400, json={"errors": {"vmid": "VM 999 does not exist"}}
            )

        client = _client_with_handler(handler)
        with pytest.raises(PMXError, match="VM 999 does not exist"):
            client.post("/nodes/pve1/qemu/999/status/start")

    def test_post_sends_form_data(self) -> None:
        """POST parameters are sent as form data with None values dropped."""
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                seen["body"] = request.content.decode()
            return httpx.Response(
                200, json={"data": "UPID:pve1:0:0:0:qmstart:101:u@p:"}
            )

        client = _client_with_handler(handler)
        client.post("/nodes/pve1/qemu/101/clone", newid=102, target=None)
        assert "newid=102" in seen["body"]
        assert "target" not in seen["body"]

    def test_no_endpoints_raises(self) -> None:
        """A context without endpoints fails clearly."""
        ctx = _make_context()
        ctx.endpoints = []
        client = ProxmoxClient(ctx, "s")
        with pytest.raises(PMXError, match="no endpoints"):
            client.connect()

    def test_failover_to_second_endpoint(self) -> None:
        """The client falls back to the next endpoint on connection errors."""
        ctx = _make_context()
        ctx.endpoints = ["down.lan:8006", "up.lan:8006"]

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "down.lan":
                raise httpx.ConnectError("refused")
            return httpx.Response(200, json={"data": {}})

        client = ProxmoxClient(ctx, "s", transport=httpx.MockTransport(handler))
        client.connect()
        assert client.get("/version") == {}
