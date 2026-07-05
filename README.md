# pmx

> Manage a Proxmox VE cluster from your terminal — no SSH, no web UI, no certs required.

`pmx` is a Python CLI for Proxmox VE that runs anywhere (built on macOS in mind) and talks
to your cluster over the Proxmox HTTP API. Every operation is a proper scriptable
subcommand; omit an argument and you get an interactive fuzzy picker instead.

## Features

- **Scriptable first** — `pmx vm start 101`, `pmx ct ls -o json | jq ...`
- **Interactive fallback** — `pmx vm start` with no ID opens a fuzzy picker showing `ID  name  node  status`
- **No CA certificates required** — full TLS verification by default, with per-context
  opt-out or SSH-style SHA-256 fingerprint pinning for self-signed clusters
- **API tokens only** — no root password; secrets resolve from env var → 1Password
  (`op://` reference) → macOS Keychain → config file
- **kubectl-style contexts** — multiple clusters/nodes, per-context endpoints with failover
- **Task-aware** — commands wait for Proxmox tasks and reflect success in exit codes;
  `--no-wait` prints the UPID, and `pmx task ls/log/wait` monitors anything
- **Safe by default** — destructive ops prompt; `destroy` requires typing the name or ID;
  `--yes` skips prompts for scripts

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- A Proxmox VE API token (Datacenter → Permissions → API Tokens)
- Optional: [1Password CLI](https://developer.1password.com/docs/cli/) for `op://` secret references

## Installation

```bash
git clone https://github.com/timmyb824/pmx.git
cd pmx
uv tool install .
```

Or for development:

```bash
uv sync --all-extras
uv run pmx --help
```

## Setup

```bash
pmx setup
```

You'll be prompted for a context name, one or more endpoints (`host[:port]`, IPs are
fine), the API user and token ID, and the token secret. If the server presents a
self-signed certificate, setup shows its SHA-256 fingerprint and offers to pin it
(recommended) or skip verification.

Config lives at `~/.config/pmx/config.toml` (0600). Secrets are stored in the macOS
Keychain by default, or referenced from 1Password with e.g.
`op://Homelab/proxmox-token/credential`. The `PMX_TOKEN_SECRET` env var overrides everything.

## Usage

```bash
# Contexts
pmx context ls
pmx context use homelab
pmx --context other-cluster node ls

# Nodes
pmx node ls
pmx node info pve1

# VMs (all commands also work with `ct` for containers)
pmx vm ls
pmx vm start 101          # or just `pmx vm start` for a picker
pmx vm shutdown 101
pmx vm info 101
pmx vm config 101
pmx vm clone 101 --name web-clone --full
pmx vm migrate 101 --target pve2 --online
pmx vm destroy 101        # type-to-confirm
pmx vm snapshot ls 101
pmx vm snapshot create 101 --name pre-upgrade
pmx vm snapshot rollback 101 --name pre-upgrade
pmx vm backup 101 --storage nas-backups

# Backups
pmx backup ls
pmx backup restore                  # picker
pmx backup delete --node pve1 <volid>

# Storage & pools
pmx storage ls
pmx storage content local --node pve1 --type iso
pmx pool create prod --comment "Production"

# Tasks
pmx task ls --running
pmx task log <UPID>
pmx task wait <UPID>

# Scripting
pmx vm ls -o json | jq '.[] | select(.status=="running") | .vmid'
pmx -y vm stop 101 --no-wait
```

## Shell completion

```bash
pmx --install-completion
```

## Development

```bash
uv sync --all-extras
uv run pytest
uv run ruff check .
```

## Roadmap

- **Phase 2** — `pmx tui`: a k9s-style live dashboard (Textual)
- **Phase 3** — `vm create` / `ct create` wizards, ISO and container template downloads

## License

MIT
