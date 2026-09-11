"""Stage-wise live monitor for an audit work dir."""

from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from benchnuke.watch import WatchSnapshot, find_latest_work, snapshot_work

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
    target = work_dir or find_latest_work()
    if target is None:
        raise FileNotFoundError("no audit.json under ./audits; pass a work dir")
    console = Console()
    with Live(console=console, refresh_per_second=max(1, int(1 / refresh)), screen=True) as live:
        while True:
            snap = snapshot_work(target)
            live.update(_render(snap, watching=target))
            if snap.run_status in {"completed", "failed"}:
                time.sleep(0.8)
                return
            time.sleep(refresh)


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
