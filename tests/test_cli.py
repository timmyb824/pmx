"""Tests for the pmx CLI entry point and context commands."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from pmx import __version__
from pmx.cli import app
from pmx.config import Config, Context, save_config

runner = CliRunner()


@pytest.fixture
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point PMX_CONFIG at a temp config with one context."""
    path = tmp_path / "config.toml"
    ctx = Context(
        name="homelab",
        endpoints=["pve1.lan:8006"],
        user="pmx@pve",
        token_id="tok",
        token_secret="inline",
    )
    save_config(Config(contexts={"homelab": ctx}, default_context="homelab"), path)
    monkeypatch.setenv("PMX_CONFIG", str(path))
    return path


class TestCli:
    """Top-level CLI behavior."""

    def test_version(self) -> None:
        """--version prints the package version."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_help_lists_groups(self) -> None:
        """Help output includes the main command groups."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for group in ("vm", "ct", "node", "backup", "storage", "pool", "task", "context"):
            assert group in result.output


class TestContextCommands:
    """pmx context subcommands against a temp config."""

    def test_context_ls(self, config_file: Path) -> None:
        """context ls shows the configured context."""
        result = runner.invoke(app, ["context", "ls"])
        assert result.exit_code == 0
        assert "homelab" in result.output

    def test_context_use_unknown_fails(self, config_file: Path) -> None:
        """Using an unknown context exits non-zero."""
        result = runner.invoke(app, ["context", "use", "nope"])
        assert result.exit_code != 0

    def test_context_remove(self, config_file: Path) -> None:
        """Removing a context updates the config file."""
        result = runner.invoke(app, ["--yes", "context", "remove", "homelab"])
        assert result.exit_code == 0
        follow_up = runner.invoke(app, ["context", "ls"])
        assert "homelab" not in follow_up.output
