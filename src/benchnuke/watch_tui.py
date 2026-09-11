"""Stage-wise live monitor for an audit work dir."""

from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from benchnuke.watch import RunSummary, WatchSnapshot, snapshot_runs, snapshot_work

_STATUS_STYLE = {
    "ok": "bold green",
    "skip": "dim",
    "running": "bold yellow",
    "error": "bold red",
    "failed": "bold red",
    "pending": "dim",
    "completed": "bold green",
}


def run_watch(work_dir: Path | None = None, *, refresh: float = 0.4) -> None:
    console = Console()
    if work_dir is None:
        _run_dashboard(console, refresh=refresh)
        return
    with Live(console=console, refresh_per_second=max(1, int(1 / refresh)), screen=True) as live:
        while True:
            snap = snapshot_work(work_dir)
            live.update(_render(snap, watching=work_dir))
            if snap.run_status in {"completed", "failed"}:
                time.sleep(0.8)
                return
            time.sleep(refresh)


def _run_dashboard(console: Console, *, refresh: float) -> None:
    base = Path("audits")
    with Live(console=console, refresh_per_second=max(1, int(1 / refresh)), screen=True) as live:
        while True:
            rows = snapshot_runs(base)
            live.update(_render_dashboard(rows, base))
            if rows and all(row.run_status in {"completed", "failed"} for row in rows):
                time.sleep(0.8)
                return
            time.sleep(refresh)


def _fmt_age(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 90 * 60:
        return f"{seconds / 60:.0f}m"
    return f"{seconds / 3600:.1f}h"


def _render_dashboard(rows: list[RunSummary], base: Path) -> Panel:
    header = Text.assemble(("bn watch", "bold cyan"), "  ", (str(base), "dim"))
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("task", min_width=24)
    table.add_column("status", min_width=9)
    table.add_column("stage", min_width=16, style="yellow")
    table.add_column("stages", justify="right")
    table.add_column("attacks", justify="right")
    table.add_column("findings C/P/R", justify="right")
    table.add_column("age", justify="right", style="dim")
    if not rows:
        table.add_row("(waiting for audits/…)", "", "", "", "", "", "")
    for row in rows:
        status = Text(row.run_status, style=_STATUS_STYLE.get(row.run_status, ""))
        task = row.task_id.rsplit("/", 1)[-1]
        table.add_row(
            task,
            status,
            row.current_stage or "—",
            f"{row.stages_done}/{row.stages_total}",
            f"{row.attacks_done}/{row.attacks_total}",
            f"{row.confirmed}/{row.probable}/{row.rejected}",
            _fmt_age(row.age_seconds),
        )
    footer = Text("bn watch <dir> for single-run detail · ctrl-c to leave", style="dim")
    return Panel(
        Group(header, Text(""), table, Text(""), footer),
        border_style="bright_black",
        padding=(1, 2),
    )


def _render(snap: WatchSnapshot, watching: Path) -> Panel:
    header = Text.assemble(
        ("bn watch", "bold cyan"),
        "  ",
        (snap.task_id, "bold"),
        "  ",
        (snap.run_status, _STATUS_STYLE.get(snap.run_status, "")),
        "  ",
        (snap.current_stage or "—", "yellow"),
    )
    stages = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    stages.add_column("#", style="dim", width=3)
    stages.add_column("stage", min_width=22)
    stages.add_column("status", min_width=10)
    if snap.stages:
        for index, row in enumerate(snap.stages, start=1):
            style = _STATUS_STYLE.get(row.status, "")
            marker = "▸" if row.name == snap.current_stage else " "
            stages.add_row(str(index), f"{marker} {row.name}", Text(row.status, style=style))
    else:
        stages.add_row("—", "(no stages yet)", "")
    log_label = str(snap.log_path) if snap.log_path else "no log"
    log = Panel(
        Text(snap.log_tail or "", style="bright_white"),
        title=f"log · {log_label}",
        border_style="cyan",
        padding=(0, 1),
    )
    footer = Text(f"{watching}   q not needed — ctrl-c to leave", style="dim")
    return Panel(
        Group(header, Text(""), stages, Text(""), log, Text(""), footer),
        border_style="bright_black",
        padding=(1, 2),
    )
