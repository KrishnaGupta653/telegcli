"""
telegcli.utils.editor
───────────────────
Open the user's $EDITOR to compose long messages.
Fully async — no blocking calls in the event loop.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path


async def open_editor(initial: str = "") -> str:
    """
    Open the system editor asynchronously.
    Returns the final text (stripped), or empty string if cancelled.
    """
    editor = (
        os.environ.get("VISUAL")
        or os.environ.get("EDITOR")
        or _find_editor()
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".telecli.txt",
        delete=False,
        encoding="utf-8",
    ) as f:
        if initial:
            f.write(initial)
        tmp_path = Path(f.name)

    try:
        proc = await asyncio.create_subprocess_exec(
            editor, str(tmp_path),
            stdin=None, stdout=None, stderr=None,
        )
        await proc.wait()
        return tmp_path.read_text(encoding="utf-8").strip()
    except Exception as e:
        from telegcli.ui.theme import print_warning
        print_warning(f"Could not open editor ({editor}): {e}")
        return ""
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _find_editor() -> str:
    for candidate in ("nano", "vi", "vim", "notepad"):
        result = subprocess.run(
            ["which", candidate],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return candidate
    return "vi"
