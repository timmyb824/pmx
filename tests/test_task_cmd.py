"""Tests for the `pmx task ls` running-task count line."""

import json
from pathlib import Path
from typing import Self

import pytest
from typer.testing import CliRunner

from pmx.cli import app
from pmx.commands import task as task_cmd
from pmx.config import Config, Context, save_config

runner = CliRunner()

FIVE_TASKS_THREE_RUNNING = [
    {"upid": "UPID:a", "type": "qmstart", "node": "pve1", "starttime": 1},
    {"upid": "UPID:b", "type": "qmstart", "node": "pve1", "starttime": 2},
    {"upid": "UPID:c", "type": "qmstart", "node": "pve1", "starttime": 3},
    {
        "upid": "UPID:d",
        "type": "qmstop",
        "node": "pve1",
        "starttime": 4,
        "endtime": 5,
        "status": "OK",
    },
    {
        "upid": "UPID:e",
        "type": "qmstop",
        "node": "pve1",
        "starttime": 6,
        "endtime": 7,
        "status": "OK",
    },
]


class FakeClient:
    """Context-manager client whose /cluster/tasks returns a fixed list."""

    def __init__(self, tasks: list[dict]) -> None:
        self.tasks = tasks

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(self, path: str) -> list[dict]:
        assert path == "/cluster/tasks"
        return [dict(t) for t in self.tasks]


@pytest.fixture
def fake_tasks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point PMX_CONFIG at a temp config and return a setter for the fake task list."""
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

    def set_tasks(tasks: list[dict]) -> None:
        monkeypatch.setattr(task_cmd, "get_client", lambda: FakeClient(tasks))

    return set_tasks


class TestTaskLsRunningCount:
    """`pmx task ls` ends with a running-task count line."""

    def test_running_count_plural(self, fake_tasks) -> None:
        fake_tasks(FIVE_TASKS_THREE_RUNNING)
        result = runner.invoke(app, ["task", "ls"])
        assert result.exit_code == 0, result.output
        assert result.output.count("3 running tasks") == 1
        assert result.output.rstrip().endswith("3 running tasks")

    def test_running_count_singular(self, fake_tasks) -> None:
        fake_tasks(FIVE_TASKS_THREE_RUNNING[2:])
        result = runner.invoke(app, ["task", "ls"])
        assert result.exit_code == 0, result.output
        assert "1 running task" in result.output
        assert "1 running tasks" not in result.output

    def test_running_count_zero(self, fake_tasks) -> None:
        fake_tasks(FIVE_TASKS_THREE_RUNNING[3:])
        result = runner.invoke(app, ["task", "ls"])
        assert result.exit_code == 0, result.output
        assert "0 running tasks" in result.output

    def test_running_count_ignores_limit(self, fake_tasks) -> None:
        fake_tasks(FIVE_TASKS_THREE_RUNNING)
        result = runner.invoke(app, ["task", "ls", "--limit", "1"])
        assert result.exit_code == 0, result.output
        assert result.output.count("UPID:") == 1
        assert "3 running tasks" in result.output

    def test_running_count_same_with_running_filter(self, fake_tasks) -> None:
        fake_tasks(FIVE_TASKS_THREE_RUNNING)
        result = runner.invoke(app, ["task", "ls", "--running"])
        assert result.exit_code == 0, result.output
        assert "3 running tasks" in result.output

    def test_json_output_has_no_running_count(self, fake_tasks) -> None:
        fake_tasks(FIVE_TASKS_THREE_RUNNING)
        result = runner.invoke(app, ["-o", "json", "task", "ls"])
        assert result.exit_code == 0, result.output
        rows = json.loads(result.output)
        assert isinstance(rows, list) and len(rows) == 5
        assert all(isinstance(row, dict) for row in rows)
        assert "running task" not in result.output
