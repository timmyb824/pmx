"""Context command group: manage connection profiles."""

import typer

from pmx.config import ConfigError, load_config, save_config
from pmx.confirm import confirm_action
from pmx.render import console, print_kv, print_table
from pmx.state import app_state

app = typer.Typer(no_args_is_help=True)

NAME_ARG = typer.Argument(..., help="Context name.")


@app.command("ls")
def ls() -> None:
    """List configured contexts."""
    config = load_config()
    rows = [
        {
            "name": ctx.name,
            "default": "*" if ctx.name == config.default_context else "",
            "endpoints": ", ".join(ctx.endpoints),
            "user": ctx.user,
            "tls": "pinned" if ctx.fingerprint else ("verify" if ctx.verify else "insecure"),
        }
        for ctx in config.contexts.values()
    ]
    print_table(
        rows,
        [
            ("Name", "name"),
            ("Default", "default"),
            ("Endpoints", "endpoints"),
            ("User", "user"),
            ("TLS", "tls"),
        ],
        title="Contexts",
        as_json=app_state.output_json,
    )


@app.command("show")
def show(name: str = NAME_ARG) -> None:
    """Show a context's settings (secrets are never displayed)."""
    config = load_config()
    ctx = config.get_context(name)
    data = ctx.to_dict()
    if not data["token_secret"].startswith("op://") and data["token_secret"] != "keyring":
        data["token_secret"] = "(inline, hidden)"
    print_kv(data, title=f"Context — {name}", as_json=app_state.output_json)


@app.command("use")
def use(name: str = NAME_ARG) -> None:
    """Set the default context."""
    config = load_config()
    config.get_context(name)
    config.default_context = name
    save_config(config)
    console.print(f"[green]done[/] — default context is now '{name}'")


@app.command("remove")
def remove(name: str = NAME_ARG) -> None:
    """Remove a context."""
    config = load_config()
    if name not in config.contexts:
        raise ConfigError(f"context '{name}' not found")
    confirm_action(f"Remove context '{name}'", app_state.yes)
    del config.contexts[name]
    if config.default_context == name:
        config.default_context = next(iter(config.contexts), "")
    save_config(config)
    console.print(f"[green]done[/] — context '{name}' removed")
