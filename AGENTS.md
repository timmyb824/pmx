# AGENTS

`pmx` is a Python 3.12 CLI and Textual TUI for managing a Proxmox VE cluster over
its HTTP API. Source is in `src/pmx/` (commands in `src/pmx/commands/`, TUI in
`src/pmx/tui/`), tests in `tests/`. See `README.md` for usage.

## Setup

```bash
uv sync --all-extras
```

There is no dev server. Run the CLI with `uv run pmx --help`. Tests never need a
real cluster; don't point anything at one.

## Validation

Same commands as `factory/checks.sh`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Run `uv run ruff format .` before committing; the gate fails unformatted code.

## Software factory

`/factory run` builds every open GitHub issue labeled `factory` through
intake → spec → build → gate → review → approve, one PR per issue. State is in
`factory/jobs/` (gitignored); `factory/bin/job` is its only writer. Checks:
`factory/checks.sh`. Dashboard: `cd factory && python3 -m http.server`, then
open http://localhost:8000/dashboard.html.

Each job works in its own git worktree, a full checkout of the repo at
`.worktrees/<job-id>` (gitignored). A tool run from the repo root that doesn't
read `.gitignore` sees those copies too; exclude `.worktrees/` in its config.
