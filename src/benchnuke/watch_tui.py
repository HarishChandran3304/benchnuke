"""Interactive multi-run audit monitor (Textual)."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Static

from benchnuke.watch import RunSummary, snapshot_runs, snapshot_work

_STATUS_STYLE = {
    "ok": "bold green",
    "skip": "dim",
    "running": "bold yellow",
    "error": "bold red",
    "failed": "bold red",
    "pending": "dim",
    "completed": "bold green",
}

_COLUMNS = ("task", "status", "stage", "stages", "attacks", "findings C/P/R", "age")


def _fmt_age(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 90 * 60:
        return f"{seconds / 60:.0f}m"
    return f"{seconds / 3600:.1f}h"


def _row_cells(row: RunSummary) -> tuple[str, ...]:
    return (
        row.task_id.rsplit("/", 1)[-1],
        row.run_status,
        row.current_stage or "—",
        f"{row.stages_done}/{row.stages_total}",
        f"{row.attacks_done}/{row.attacks_total}",
        f"{row.confirmed}/{row.probable}/{row.rejected}",
        _fmt_age(row.age_seconds),
    )


class DashboardScreen(Screen[None]):
    BINDINGS = [Binding("o", "open_run", "Open run")]

    def __init__(self, base: Path, *, refresh: float) -> None:
        super().__init__()
        self.base = base
        self._refresh_interval = refresh
        self._row_dirs: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static(" bn watch", id="title")
        yield DataTable(cursor_type="row", zebra_stripes=True)
        yield Static(" ↑/↓ select · enter/o open · q quit ", id="hint")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        for column in _COLUMNS:
            table.add_column(column)
        self.refresh_rows()
        self.set_interval(self._refresh_interval, self.refresh_rows)

    def refresh_rows(self) -> None:
        rows = snapshot_runs(self.base)
        table = self.query_one(DataTable)
        cursor = table.cursor_row if table.row_count else 0
        table.clear()
        self._row_dirs = []
        if not rows:
            table.add_row("(waiting for audits/…)", "", "", "", "", "", "")
            return
        for row in rows:
            table.add_row(*_row_cells(row))
            self._row_dirs.append(str(row.work_dir))
        if cursor < table.row_count:
            table.move_cursor(row=cursor)

    def action_open_run(self) -> None:
        table = self.query_one(DataTable)
        if 0 <= table.cursor_row < len(self._row_dirs):
            self.app.push_screen(
                RunDetailScreen(
                    Path(self._row_dirs[table.cursor_row]),
                    refresh=self._refresh_interval,
                )
            )

    def on_data_table_row_selected(self, _event: DataTable.RowSelected) -> None:
        self.action_open_run()


class RunDetailScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("backspace", "back", "Back"),
    ]

    def __init__(self, work_dir: Path, *, refresh: float) -> None:
        super().__init__()
        self.work_dir = work_dir
        self._refresh_interval = refresh

    def compose(self) -> ComposeResult:
        yield Static(id="summary")
        yield DataTable(id="stages", cursor_type="none", zebra_stripes=True)
        yield Static(id="log")
        yield Static(" esc back · q quit ", id="hint")

    def on_mount(self) -> None:
        stages = self.query_one("#stages", DataTable)
        stages.add_columns("#", "stage", "status")
        self.refresh_detail()
        self.set_interval(self._refresh_interval, self.refresh_detail)

    def refresh_detail(self) -> None:
        snap = snapshot_work(self.work_dir)
        summary = self.query_one("#summary", Static)
        summary.update(
            f" bn watch · {snap.task_id} · {snap.run_status} · {snap.current_stage or '—'}"
        )
        stages = self.query_one("#stages", DataTable)
        stages.clear()
        if snap.stages:
            for index, row in enumerate(snap.stages, start=1):
                marker = "▸" if row.name == snap.current_stage else " "
                stages.add_row(str(index), f"{marker} {row.name}", row.status)
        else:
            stages.add_row("—", "(no stages yet)", "")
        log = self.query_one("#log", Static)
        label = str(snap.log_path) if snap.log_path else "no log"
        log.update(f"\n log · {label}\n{snap.log_tail}")

    def action_back(self) -> None:
        self.app.pop_screen()


class AuditWatchApp(App[None]):
    """bn watch: dashboard of all runs; enter drills into one."""

    BINDINGS = [Binding("q", "quit", "Quit")]
    CSS = """
    #title { text-style: bold; color: cyan; padding: 0 1; }
    #hint { color: $text-muted; padding: 0 1; }
    #summary { text-style: bold; padding: 0 1; }
    #stages { height: auto; max-height: 60%; }
    #log { color: $text; padding: 0 1; }
    DataTable { height: auto; }
    """

    def __init__(self, work_dir: Path | None, *, base: Path, refresh: float) -> None:
        super().__init__()
        self.work_dir = work_dir
        self.base = base
        self._refresh_interval = refresh

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen(self.base, refresh=self._refresh_interval))
        if self.work_dir is not None:
            self.push_screen(RunDetailScreen(self.work_dir, refresh=self._refresh_interval))


def run_watch(
    work_dir: Path | None = None, *, refresh: float = 0.4, base: Path = Path("audits")
) -> None:
    AuditWatchApp(work_dir, base=base, refresh=refresh).run()
