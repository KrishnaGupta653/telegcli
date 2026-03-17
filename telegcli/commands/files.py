"""
telegcli.commands.files
─────────────────────
Commands: upload, download

Fix #8: no blocking I/O in async context
"""

from __future__ import annotations

import logging
from pathlib import Path

from telegcli.core.client import tg
from telegcli.core.config import get_config
from telegcli.ui.theme import (
    get_console, print_success, print_error, print_warning, entity_name,
)
from telegcli.ui.progress import UploadProgress, DownloadProgress
from telegcli.utils.resolver import resolve_entity

log = logging.getLogger("telegcli.files")


async def cmd_upload(args: list[str]) -> None:
    """upload <chat> <file_path> [caption]"""
    if len(args) < 2:
        print_error("Usage: upload <chat> <file_path> [caption]")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    file_path = Path(args[1]).expanduser()
    if not file_path.exists():
        print_error(f"File not found: {file_path}")
        return
    if not file_path.is_file():
        print_error(f"Not a file: {file_path}")
        return

    caption = " ".join(args[2:]) if len(args) > 2 else ""
    filename = file_path.name
    size_mb = file_path.stat().st_size / 1_048_576

    console = get_console()
    console.print(
        f"  Uploading [bold]{filename}[/] ({size_mb:.1f} MB) "
        f"to [bold]{entity_name(entity)}[/]…"
    )

    with UploadProgress(filename) as progress:
        msg = await tg.upload_file(
            entity, file_path, caption=caption,
            progress_callback=progress.callback,
        )

    print_success(f"Uploaded #{msg.id}  →  {entity_name(entity)}")
    log.info("Uploaded %s to %s as #%d", filename, entity_name(entity), msg.id)


async def cmd_download(args: list[str]) -> None:
    """download <chat> <msg_id> [destination_dir]"""
    if len(args) < 2:
        print_error("Usage: download <chat> <msg_id> [destination]")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    try:
        msg_id = int(args[1])
    except ValueError:
        print_error("msg_id must be an integer.")
        return

    cfg = get_config()
    dest = Path(args[2]).expanduser() if len(args) > 2 else cfg.download_dir

    try:
        msg = await tg.raw.get_messages(entity, ids=msg_id)
    except Exception as e:
        print_error(f"Could not fetch message #{msg_id}: {e}")
        return

    if msg is None:
        print_error(f"Message #{msg_id} not found.")
        return

    if not msg.media:
        print_warning(f"Message #{msg_id} has no media to download.")
        return

    media_type = type(msg.media).__name__.replace("MessageMedia", "")
    get_console().print(f"  Downloading [{media_type}] from #{msg_id}…")

    with DownloadProgress(f"msg_{msg_id}") as progress:
        path = await tg.download_media(
            msg, destination=dest, progress_callback=progress.callback,
        )

    if path:
        print_success(f"Saved → {path}")
        log.info("Downloaded msg #%d to %s", msg_id, path)
    else:
        print_warning("Nothing was downloaded.")
