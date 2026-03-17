"""
telegcli.ui.progress
─────────────────
Rich-based progress bars and spinners for file transfers.

Fix #19: removed dead `p = get_console()` in spinner()
"""

from __future__ import annotations

import time
from typing import Optional

from rich.progress import (
    Progress, BarColumn, TextColumn, TransferSpeedColumn,
    TimeRemainingColumn, FileSizeColumn, TotalFileSizeColumn,
    SpinnerColumn, TaskID,
)
from telegcli.ui.theme import get_console


def make_transfer_progress(label: str = "Transferring") -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn(f"[bold blue]{label}[/]  [cyan]{{task.fields[filename]}}[/]"),
        BarColumn(),
        FileSizeColumn(),
        TextColumn("/"),
        TotalFileSizeColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=get_console(),
        transient=True,
    )


class UploadProgress:
    def __init__(self, filename: str) -> None:
        self._progress = make_transfer_progress("Uploading")
        self._task: Optional[TaskID] = None
        self._filename = filename

    def __enter__(self):
        self._progress.__enter__()
        return self

    def __exit__(self, *args):
        self._progress.__exit__(*args)

    def callback(self, current: int, total: int) -> None:
        if self._task is None:
            self._task = self._progress.add_task(
                "upload", total=total, filename=self._filename,
            )
        self._progress.update(self._task, completed=current)


class DownloadProgress:
    def __init__(self, filename: str = "file") -> None:
        self._progress = make_transfer_progress("Downloading")
        self._task: Optional[TaskID] = None
        self._filename = filename

    def __enter__(self):
        self._progress.__enter__()
        return self

    def __exit__(self, *args):
        self._progress.__exit__(*args)

    def callback(self, current: int, total: int) -> None:
        if self._task is None:
            self._task = self._progress.add_task(
                "download", total=total, filename=self._filename,
            )
        self._progress.update(self._task, completed=current)


class SpinnerContext:
    """Context manager: show a spinner with a message. Fix #19: no dead code."""

    def __init__(self, message: str) -> None:
        self._message = message
        self._live = None

    def __enter__(self):
        from rich.live import Live
        from rich.text import Text
        self._live = Live(
            Text(f"⠋ {self._message}", style="bold blue"),
            console=get_console(),
            transient=True,
        )
        self._live.__enter__()
        return self

    def __exit__(self, *args):
        if self._live:
            self._live.__exit__(*args)


def spinner(message: str) -> SpinnerContext:
    return SpinnerContext(message)
