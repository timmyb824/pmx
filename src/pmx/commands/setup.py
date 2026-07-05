"""Interactive first-run setup: create a context, choose TLS mode, store the secret."""

import typer

from pmx.client import PMXError, check_endpoint_certificate, get_server_fingerprint
from pmx.config import (
    KEYRING_SENTINEL,
    OP_PREFIX,
    Context,
    load_config,
    save_config,
    store_keyring_secret,
)
from pmx.render import console


def _choose_tls_mode(ctx: Context) -> None:
    """Detect the first endpoint's certificate and configure the TLS mode."""
    endpoint = ctx.endpoints[0]
    console.print(f"Checking certificate on [bold]{endpoint}[/]...")
    if check_endpoint_certificate(endpoint):
        console.print("[green]Certificate verifies cleanly — using full TLS verification.[/]")
        ctx.verify = True
        return
    console.print("[yellow]Certificate does not pass standard verification (self-signed?).[/]")
    try:
        fingerprint = get_server_fingerprint(endpoint)
        console.print(f"Server certificate SHA-256 fingerprint:\n  [bold]{fingerprint}[/]")
    except (PMXError, OSError) as exc:
        raise PMXError(f"could not inspect certificate on {endpoint}: {exc}") from exc
    choice = typer.prompt(
        "Choose TLS mode: [p]in this fingerprint (recommended) / [s]kip verification",
        default="p",
    ).lower()
    if choice.startswith("p"):
        ctx.fingerprint = fingerprint
        ctx.verify = False
        console.print("[green]Fingerprint pinned.[/]")
    else:
        ctx.verify = False
        console.print("[yellow]TLS verification disabled for this context.[/]")


def run_setup() -> None:
    """Interactively create or update a pmx context."""
    console.print("[bold]pmx setup[/] — configure a Proxmox VE connection\n")
    name = typer.prompt("Context name", default="default").strip()
    endpoints_raw = typer.prompt(
        "Endpoint(s), space-separated host[:port] (e.g. 'pve1.lan:8006 10.0.0.2')"
    )
    endpoints = [e if ":" in e else f"{e}:8006" for e in endpoints_raw.split()]
    user = typer.prompt("API user (e.g. root@pam or pmx@pve)").strip()
    token_id = typer.prompt("API token ID (the token name, not the secret)").strip()

    ctx = Context(name=name, endpoints=endpoints, user=user, token_id=token_id)
    _choose_tls_mode(ctx)

    console.print(
        "\nWhere is the token secret?\n"
        "  [bold]1[/] Enter it now, store in the system keychain (recommended)\n"
        "  [bold]2[/] 1Password reference (op://Vault/Item/field)\n"
        "  [bold]3[/] Enter it now, store inline in the config file"
    )
    choice = typer.prompt("Choice", default="1").strip()
    if choice == "2":
        ref = typer.prompt("1Password secret reference").strip()
        if not ref.startswith(OP_PREFIX):
            raise PMXError(f"reference must start with {OP_PREFIX}")
        ctx.token_secret = ref
    else:
        secret = typer.prompt("Token secret", hide_input=True).strip()
        if choice == "3":
            ctx.token_secret = secret
        else:
            ctx.token_secret = KEYRING_SENTINEL
            store_keyring_secret(ctx, secret)

    config = load_config()
    config.contexts[name] = ctx
    if not config.default_context:
        config.default_context = name
    save_config(config)
    console.print(f"\n[green]done[/] — context '{name}' saved. Try: [bold]pmx node ls[/]")
