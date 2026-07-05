"""Tests for pmx.config: contexts, persistence, and secret resolution."""

from pathlib import Path

import pytest

from pmx.config import (
    Config,
    ConfigError,
    Context,
    load_config,
    resolve_secret,
    save_config,
)


def _make_context(**overrides: object) -> Context:
    """Build a test context with sensible defaults."""
    defaults: dict = {
        "name": "homelab",
        "endpoints": ["pve1.lan:8006", "pve2.lan:8006"],
        "user": "pmx@pve",
        "token_id": "pmx-token",
        "token_secret": "inline-secret",
    }
    defaults.update(overrides)
    return Context(**defaults)


class TestConfigPersistence:
    """Round-trip and defaults for TOML persistence."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """A saved config loads back with identical contexts."""
        path = tmp_path / "config.toml"
        ctx = _make_context(fingerprint="AA:BB", verify=False)
        save_config(Config(contexts={"homelab": ctx}, default_context="homelab"), path)
        loaded = load_config(path)
        assert loaded.default_context == "homelab"
        assert loaded.contexts["homelab"] == ctx

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Loading a non-existent path yields an empty config."""
        config = load_config(tmp_path / "nope.toml")
        assert config.contexts == {}
        assert config.default_context == ""

    def test_saved_file_has_0600_permissions(self, tmp_path: Path) -> None:
        """The config file must not be world-readable."""
        path = tmp_path / "config.toml"
        save_config(Config(contexts={"c": _make_context(name="c")}, default_context="c"), path)
        assert path.stat().st_mode & 0o777 == 0o600


class TestGetContext:
    """Context lookup behavior."""

    def test_default_context_used_when_name_omitted(self) -> None:
        """get_context falls back to the default context."""
        ctx = _make_context()
        config = Config(contexts={"homelab": ctx}, default_context="homelab")
        assert config.get_context() is ctx

    def test_missing_context_raises(self) -> None:
        """Unknown context names raise ConfigError."""
        config = Config(contexts={}, default_context="")
        with pytest.raises(ConfigError):
            config.get_context("nope")


class TestResolveSecret:
    """Secret resolution order: env, op://, keyring, inline."""

    def test_env_var_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PMX_TOKEN_SECRET overrides everything."""
        monkeypatch.setenv("PMX_TOKEN_SECRET", "from-env")
        assert resolve_secret(_make_context()) == "from-env"

    def test_inline_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An inline config value is returned as-is."""
        monkeypatch.delenv("PMX_TOKEN_SECRET", raising=False)
        assert resolve_secret(_make_context(token_secret="inline-secret")) == "inline-secret"

    def test_op_reference_uses_op_cli(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """op:// references shell out to `op read`."""
        monkeypatch.delenv("PMX_TOKEN_SECRET", raising=False)

        def fake_run(cmd: list[str], **kwargs: object) -> object:
            assert cmd == ["op", "read", "op://Vault/pve/credential"]

            class Result:
                stdout = "from-op\n"

            return Result()

        monkeypatch.setattr("pmx.config.subprocess.run", fake_run)
        ctx = _make_context(token_secret="op://Vault/pve/credential")
        assert resolve_secret(ctx) == "from-op"

    def test_keyring_missing_secret_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A keyring sentinel with no stored secret raises ConfigError."""
        monkeypatch.delenv("PMX_TOKEN_SECRET", raising=False)
        monkeypatch.setattr("pmx.config.keyring.get_password", lambda *a: None)
        with pytest.raises(ConfigError):
            resolve_secret(_make_context(token_secret="keyring"))
