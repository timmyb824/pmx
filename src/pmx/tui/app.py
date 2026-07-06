"""Textual k9s-style dashboard: nodes/VMs/CTs/tasks panes with live refresh."""

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Label, TabbedContent, TabPane

from pmx.client import PMXError, ProxmoxClient
from pmx.state import get_client
from pmx.tui.data import (
    GUEST_COLUMNS,
    NODE_COLUMNS,
    TASK_COLUMNS,
    Snapshot,
    fetch_snapshot,
)

REFRESH_INTERVAL = 5.0

STATUS_STYLES = {
    "running": "green",
    "online": "green",
    "OK": "green",
    "stopped": "red",
    "offline": "red",
    "paused": "yellow",
    "suspended": "yellow",
}

PANE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "nodes": NODE_COLUMNS,
    "vms": GUEST_COLUMNS,
    "cts": GUEST_COLUMNS,
    "tasks": TASK_COLUMNS,
}

GUEST_ACTIONS = {"start", "shutdown", "stop"}


def _cell(row: dict, key: str) -> Text | str:
    """Render a row value as a table cell, coloring known statuses."""
    value = row.get(key)
    text = "-" if value is None or value == "" else str(value)
    if key == "status" and (style := STATUS_STYLES.get(text)):
        return Text(text, style=style)
    return text


class ConfirmScreen(ModalScreen[bool]):
    """A modal yes/no confirmation dialog."""

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "No", show=False),
    ]

    def __init__(self, prompt: str) -> None:
        """Store the prompt to display."""
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        """Lay out the prompt and the key hints."""
        with Vertical(id="confirm-box"):
            yield Label(self._prompt, id="confirm-prompt")
            yield Label("[b]y[/b]es / [b]n[/b]o", id="confirm-hint")

    def action_confirm(self) -> None:
        """Dismiss with a positive answer."""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Dismiss with a negative answer."""
        self.dismiss(False)


class PmxTuiApp(App[None]):
    """The pmx dashboard application."""

    TITLE = "pmx"
    CSS = """
    DataTable {
        height: 1fr;
    }
    ConfirmScreen {
        align: center middle;
    }
    #confirm-box {
        width: auto;
        max-width: 80%;
        height: auto;
        padding: 1 3;
        border: thick $accent;
        background: $surface;
    }
    #confirm-hint {
        margin-top: 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("1", "show_pane('nodes')", "Nodes"),
        Binding("2", "show_pane('vms')", "VMs"),
        Binding("3", "show_pane('cts')", "CTs"),
        Binding("4", "show_pane('tasks')", "Tasks"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "guest_action('start')", "Start"),
        Binding("t", "guest_action('shutdown')", "Shutdown"),
        Binding("x", "guest_action('stop')", "Stop"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        client: ProxmoxClient,
        refresh_interval: float = REFRESH_INTERVAL,
    ) -> None:
        """Create the dashboard around an existing (possibly unconnected) client."""
        super().__init__()
        self.client = client
        self.refresh_interval = refresh_interval
        self.snapshot = Snapshot()
        self.sub_title = client.ctx.name

    def compose(self) -> ComposeResult:
        """Lay out the header, tabbed panes, and footer."""
        yield Header(show_clock=True)
        with TabbedContent(initial="nodes"):
            for pane_id, title in (
                ("nodes", "Nodes"),
                ("vms", "VMs"),
                ("cts", "CTs"),
                ("tasks", "Tasks"),
            ):
                with TabPane(title, id=pane_id):
                    yield DataTable(id=f"table-{pane_id}", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize table columns, start the refresh timer, and load data."""
        for pane_id, columns in PANE_COLUMNS.items():
            table = self.query_one(f"#table-{pane_id}", DataTable)
            for header, key in columns:
                table.add_column(header, key=key)
        self.set_interval(self.refresh_interval, self.refresh_data)
        self.refresh_data()

    @work(thread=True, exclusive=True, group="refresh")
    def refresh_data(self) -> None:
        """Fetch a cluster snapshot in a worker thread and apply it to the UI."""
        try:
            snapshot = fetch_snapshot(self.client)
        except PMXError as exc:
            self.call_from_thread(self.notify, str(exc), severity="error", timeout=8)
            return
        self.call_from_thread(self.apply_snapshot, snapshot)

    def apply_snapshot(self, snapshot: Snapshot) -> None:
        """Replace all pane contents with a new snapshot, preserving cursor rows."""
        self.snapshot = snapshot
        for pane_id, rows in (
            ("nodes", snapshot.nodes),
            ("vms", snapshot.vms),
            ("cts", snapshot.cts),
            ("tasks", snapshot.tasks),
        ):
            self._fill_table(pane_id, rows)

    def _fill_table(self, pane_id: str, rows: list[dict]) -> None:
        """Rewrite one pane's table rows, keeping the cursor near its position."""
        table = self.query_one(f"#table-{pane_id}", DataTable)
        cursor = table.cursor_row
        table.clear()
        for row in rows:
            table.add_row(*(_cell(row, key) for _, key in PANE_COLUMNS[pane_id]))
        if table.row_count:
            table.move_cursor(row=min(cursor, table.row_count - 1))

    def action_show_pane(self, pane_id: str) -> None:
        """Switch to a pane and focus its table."""
        self.query_one(TabbedContent).active = pane_id
        self.query_one(f"#table-{pane_id}", DataTable).focus()

    def action_refresh(self) -> None:
        """Trigger an immediate data refresh."""
        self.refresh_data()

    def _selected_guest(self) -> tuple[str, dict] | None:
        """Return (kind, row) for the guest under the cursor, or None."""
        pane_id = self.query_one(TabbedContent).active
        if pane_id not in ("vms", "cts"):
            return None
        rows = self.snapshot.vms if pane_id == "vms" else self.snapshot.cts
        table = self.query_one(f"#table-{pane_id}", DataTable)
        if not rows or table.cursor_row >= len(rows):
            return None
        kind = "qemu" if pane_id == "vms" else "lxc"
        return kind, rows[table.cursor_row]

    def action_guest_action(self, operation: str) -> None:
        """Confirm and run a lifecycle action on the selected VM or container."""
        if operation not in GUEST_ACTIONS:
            return
        if (selected := self._selected_guest()) is None:
            self.notify("select a VM or CT first", severity="warning")
            return
        kind, row = selected
        noun = "VM" if kind == "qemu" else "CT"
        label = f"{noun} {row['vmid']} ({row['name']})"
        path = f"/nodes/{row['node']}/{kind}/{row['vmid']}/status/{operation}"

        def on_answer(confirmed: bool | None) -> None:
            """Run the action if the user confirmed."""
            if confirmed:
                self._run_guest_action(path, operation, label)

        self.push_screen(ConfirmScreen(f"{operation} {label}?"), on_answer)

    @work(thread=True, group="actions")
    def _run_guest_action(self, path: str, operation: str, label: str) -> None:
        """POST a lifecycle action in a worker thread and refresh afterwards."""
        try:
            self.client.post(path)
        except PMXError as exc:
            self.call_from_thread(self.notify, str(exc), severity="error", timeout=8)
            return
        self.call_from_thread(self.notify, f"{operation} requested for {label}")
        self.refresh_data()


def run_tui(client: ProxmoxClient | None = None) -> None:
    """Launch the dashboard, building a client from the active context if needed."""
    if client is None:
        client = get_client()
    try:
        PmxTuiApp(client).run()
    finally:
        client.close()
