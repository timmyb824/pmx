"""Thin httpx client for the Proxmox VE HTTP API.

Supports three TLS modes per context: full verification (default), verification
disabled, and SHA-256 fingerprint pinning (trust-on-first-use).
"""

import hashlib
import socket
import ssl
from typing import Any

import httpx

from pmx.config import Context

DEFAULT_PORT = 8006
DEFAULT_TIMEOUT = 30.0


class PMXError(Exception):
    """Raised for API errors, connection failures, and fingerprint mismatches."""


def split_endpoint(endpoint: str) -> tuple[str, int]:
    """Split a 'host:port' endpoint string into (host, port), defaulting to 8006."""
    host, _, port = endpoint.partition(":")
    return host, int(port) if port else DEFAULT_PORT


def get_server_fingerprint(endpoint: str, timeout: float = 10.0) -> str:
    """Fetch the server certificate and return its SHA-256 fingerprint (colon-separated hex)."""
    host, port = split_endpoint(endpoint)
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    if der is None:
        raise PMXError(f"could not retrieve certificate from {endpoint}")
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def check_endpoint_certificate(endpoint: str, timeout: float = 10.0) -> bool:
    """Return True if the endpoint's certificate passes standard verification."""
    host, port = split_endpoint(endpoint)
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host):
                return True
    except ssl.SSLError:
        return False


class ProxmoxClient:
    """A minimal Proxmox VE API client with endpoint failover and token auth."""

    def __init__(
        self,
        ctx: Context,
        secret: str,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create a client for a context using the resolved token secret."""
        self.ctx = ctx
        self._timeout = timeout
        self._transport = transport
        self._client: httpx.Client | None = None
        self._auth_header = f"PVEAPIToken={ctx.user}!{ctx.token_id}={secret}"

    def _verify_mode(self) -> ssl.SSLContext | bool:
        """Return the httpx verify argument for this context's TLS mode."""
        if self.ctx.fingerprint:
            insecure = ssl.create_default_context()
            insecure.check_hostname = False
            insecure.verify_mode = ssl.CERT_NONE
            return insecure
        return self.ctx.verify

    def _build_client(self, endpoint: str) -> httpx.Client:
        """Build an httpx client bound to a specific endpoint."""
        host, port = split_endpoint(endpoint)
        return httpx.Client(
            base_url=f"https://{host}:{port}/api2/json",
            headers={"Authorization": self._auth_header},
            verify=self._verify_mode(),
            timeout=self._timeout,
            transport=self._transport,
        )

    def _pin_check(self, endpoint: str) -> None:
        """Verify the endpoint's certificate fingerprint against the pinned value."""
        actual = get_server_fingerprint(endpoint)
        if actual != self.ctx.fingerprint.upper():
            raise PMXError(
                f"certificate fingerprint mismatch for {endpoint}:\n"
                f"  pinned: {self.ctx.fingerprint.upper()}\n"
                f"  actual: {actual}\n"
                "The server certificate changed. If this is expected, re-run 'pmx setup'."
            )

    def connect(self) -> None:
        """Connect to the first reachable endpoint, applying fingerprint pinning if set."""
        if self._client is not None:
            return
        if not self.ctx.endpoints:
            raise PMXError(f"context '{self.ctx.name}' has no endpoints configured")
        errors: list[str] = []
        for endpoint in self.ctx.endpoints:
            try:
                if self.ctx.fingerprint and self._transport is None:
                    self._pin_check(endpoint)
                client = self._build_client(endpoint)
                client.get("/version")
                self._client = client
                return
            except (httpx.TransportError, OSError, PMXError) as exc:
                errors.append(f"{endpoint}: {exc}")
        details = "\n  ".join(errors)
        raise PMXError(f"could not reach any endpoint:\n  {details}")

    def close(self) -> None:
        """Close the underlying HTTP connection."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def request(self, method: str, path: str, **params: Any) -> Any:
        """Issue an API request and return the response's 'data' field."""
        self.connect()
        assert self._client is not None
        kwargs: dict[str, Any] = {}
        clean = {k: v for k, v in params.items() if v is not None}
        if method == "GET":
            kwargs["params"] = clean
        elif clean:
            kwargs["data"] = clean
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise PMXError(f"request failed: {exc}") from exc
        if response.status_code >= 400:
            raise PMXError(self._error_message(response, method, path))
        return response.json().get("data")

    @staticmethod
    def _error_message(response: httpx.Response, method: str, path: str) -> str:
        """Build a readable error message from an API error response."""
        detail = response.reason_phrase
        try:
            body = response.json()
            if errors := body.get("errors"):
                detail = "; ".join(f"{k}: {v}" for k, v in errors.items())
            elif message := body.get("message"):
                detail = str(message).strip()
        except ValueError:
            pass
        return f"{method} {path} failed ({response.status_code}): {detail}"

    def get(self, path: str, **params: Any) -> Any:
        """GET a path and return its data."""
        return self.request("GET", path, **params)

    def post(self, path: str, **params: Any) -> Any:
        """POST to a path and return its data (often a task UPID)."""
        return self.request("POST", path, **params)

    def put(self, path: str, **params: Any) -> Any:
        """PUT to a path and return its data."""
        return self.request("PUT", path, **params)

    def delete(self, path: str, **params: Any) -> Any:
        """DELETE a path and return its data (often a task UPID)."""
        return self.request("DELETE", path, **params)

    def __enter__(self) -> "ProxmoxClient":
        """Enter a context manager, connecting lazily on first request."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the client on context exit."""
        self.close()
