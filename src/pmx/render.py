"""Output rendering: Rich tables for humans, JSON for scripts."""

import json
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


def print_json(data: Any) -> None:
    """Print data as pretty JSON."""
    console.print_json(json.dumps(data, default=str))


def print_table(
    rows: list[dict],
    columns: list[tuple[str, str]],
    title: str = "",
    as_json: bool = False,
) -> None:
    """Render rows as a Rich table (or JSON).

    Columns are (header, key) pairs; missing values render as '-'.
    """
    if as_json:
        print_json(rows)
        return
    table = Table(title=title or None, header_style="bold cyan")
    for header, _ in columns:
        table.add_column(header)
    for row in rows:
        table.add_row(*(_fmt(row.get(key)) for _, key in columns))
    console.print(table)


def print_kv(data: dict, title: str = "", as_json: bool = False) -> None:
    """Render a single object as a key/value table (or JSON)."""
    if as_json:
        print_json(data)
        return
    table = Table(title=title or None, show_header=False, box=None, pad_edge=False)
    table.add_column(style="bold cyan")
    table.add_column()
    for key in sorted(data):
        table.add_row(str(key), _fmt(data[key]))
    console.print(table)


def _fmt(value: Any) -> str:
    """Format a cell value for table display."""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def fmt_bytes(value: Any) -> str:
    """Format a byte count as a human-readable string."""
    if not isinstance(value, (int, float)):
        return "-"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def fmt_uptime(value: Any) -> str:
    """Format an uptime in seconds as 'Xd Yh Zm'."""
    if not isinstance(value, (int, float)) or value <= 0:
        return "-"
    total = int(value)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return f"{days}d {hours}h {minutes}m"
