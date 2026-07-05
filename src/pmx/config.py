"""Configuration: named contexts, TOML persistence, and secret resolution."""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import keyring
import tomlkit

ENV_TOKEN_SECRET = "PMX_TOKEN_SECRET"
ENV_CONFIG_PATH = "PMX_CONFIG"
KEYRING_SERVICE = "pmx"
KEYRING_SENTINEL = "keyring"
OP_PREFIX = "op://"


class ConfigError(Exception):
    """Raised for configuration problems (missing context, unresolved secret, etc.)."""


@dataclass
class Context:
    """A named connection profile for a Proxmox cluster or standalone node."""

    name: str
    endpoints: list[str] = field(default_factory=list)
    user: str = ""
    token_id: str = ""
    token_secret: str = KEYRING_SENTINEL
    verify: bool = True
    fingerprint: str = ""

    def keyring_account(self) -> str:
        """Return the keyring account name used to store this context's token secret."""
        return f"{self.name}:{self.user}!{self.token_id}"

    def to_dict(self) -> dict:
        """Serialize this context to a plain dict for TOML output."""
        return {
            "endpoints": self.endpoints,
            "user": self.user,
            "token_id": self.token_id,
            "token_secret": self.token_secret,
            "verify": self.verify,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "Context":
        """Build a context from a TOML table."""
        return cls(
            name=name,
            endpoints=list(data.get("endpoints", [])),
            user=str(data.get("user", "")),
            token_id=str(data.get("token_id", "")),
            token_secret=str(data.get("token_secret", KEYRING_SENTINEL)),
            verify=bool(data.get("verify", True)),
            fingerprint=str(data.get("fingerprint", "")),
        )


@dataclass
class Config:
    """The full pmx configuration: all contexts plus the default context name."""

    contexts: dict[str, Context] = field(default_factory=dict)
    default_context: str = ""

    def get_context(self, name: str | None = None) -> Context:
        """Return the named context, or the default context when name is None."""
        target = name or self.default_context
        if not target:
            raise ConfigError("no context specified and no default context set; run 'pmx setup'")
        if (ctx := self.contexts.get(target)) is None:
            raise ConfigError(f"context '{target}' not found; run 'pmx context ls'")
        return ctx


def config_path() -> Path:
    """Return the config file path, honoring PMX_CONFIG and XDG_CONFIG_HOME."""
    if env_path := os.environ.get(ENV_CONFIG_PATH):
        return Path(env_path)
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg) / "pmx" / "config.toml"


def load_config(path: Path | None = None) -> Config:
    """Load configuration from disk, returning an empty Config if the file is absent."""
    path = path or config_path()
    if not path.exists():
        return Config()
    doc = tomlkit.parse(path.read_text())
    contexts = {
        name: Context.from_dict(name, dict(table))
        for name, table in dict(doc.get("contexts", {})).items()
    }
    return Config(contexts=contexts, default_context=str(doc.get("default_context", "")))


def save_config(config: Config, path: Path | None = None) -> None:
    """Write configuration to disk with 0600 permissions."""
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.document()
    doc["default_context"] = config.default_context
    contexts = tomlkit.table()
    for name, ctx in config.contexts.items():
        contexts[name] = ctx.to_dict()
    doc["contexts"] = contexts
    path.write_text(tomlkit.dumps(doc))
    path.chmod(0o600)


def _read_op_secret(reference: str) -> str:
    """Resolve a 1Password secret reference (op://...) via the `op` CLI."""
    try:
        result = subprocess.run(
            ["op", "read", reference],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise ConfigError("1Password CLI ('op') not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise ConfigError(f"'op read {reference}' failed: {exc.stderr.strip()}") from exc
    return result.stdout.strip()


def resolve_secret(ctx: Context) -> str:
    """Resolve the API token secret for a context.

    Resolution order: PMX_TOKEN_SECRET env var, 1Password op:// reference,
    macOS Keychain (via keyring), then inline config value.
    """
    if env_secret := os.environ.get(ENV_TOKEN_SECRET):
        return env_secret
    ref = ctx.token_secret
    if ref.startswith(OP_PREFIX):
        return _read_op_secret(ref)
    if ref == KEYRING_SENTINEL or not ref:
        if secret := keyring.get_password(KEYRING_SERVICE, ctx.keyring_account()):
            return secret
        raise ConfigError(
            f"no token secret found in keychain for context '{ctx.name}'; re-run 'pmx setup'"
        )
    return ref


def store_keyring_secret(ctx: Context, secret: str) -> None:
    """Store a token secret in the system keychain for a context."""
    keyring.set_password(KEYRING_SERVICE, ctx.keyring_account(), secret)
