"""Shared runtime state for the CLI (global flags and client construction)."""

from dataclasses import dataclass

from pmx.client import ProxmoxClient
from pmx.config import load_config, resolve_secret


@dataclass
class AppState:
    """Global flag values collected by the root Typer callback."""

    context_name: str | None = None
    output_json: bool = False
    yes: bool = False
    no_wait: bool = False


app_state = AppState()


def get_client() -> ProxmoxClient:
    """Build a ProxmoxClient for the active context using the resolved secret."""
    config = load_config()
    ctx = config.get_context(app_state.context_name)
    secret = resolve_secret(ctx)
    return ProxmoxClient(ctx, secret)
