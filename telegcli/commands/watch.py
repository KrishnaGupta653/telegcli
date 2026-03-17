"""
telegcli.commands.watch
─────────────────────
Real-time message streaming.

Fixes applied:
  #6 — Uses remove_watch_handlers() so automation engine is untouched
  #6 — Proper asyncio.Event stop mechanism instead of magic sleep(86400)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from rich.rule import Rule
from rich.text import Text

from telegcli.core.client import tg
from telegcli.ui.theme import (
    get_console, get_palette, entity_name, format_ts,
)
from telegcli.utils.resolver import resolve_entity

log = logging.getLogger("telegcli.watch")


async def cmd_watch(args: list[str]) -> None:
    """
    watch            → stream all incoming messages
    watch <chat>     → stream only from specific chat
    watch <chat> --out  → include outgoing too
    """
    console = get_console()
    p = get_palette()

    filter_entity = None
    filter_id: Optional[int] = None
    include_out = "--out" in args
    clean_args = [a for a in args if a != "--out"]

    if clean_args:
        filter_entity = await resolve_entity(clean_args[0])
        if filter_entity:
            filter_id = filter_entity.id

    scope = entity_name(filter_entity) if filter_entity else "all chats"
    console.print(
        Rule(
            f"[{p['accent']}]Watching[/] [{p['dim']}]{scope}[/] "
            f"[{p['dim']}]— Ctrl+C to stop[/]",
            style=p["separator"],
        )
    )

    me_id = tg.me.id if tg.me else 0
    stop_event = asyncio.Event()

    async def handler(event):
        msg = event.message
        if filter_id and getattr(event, "chat_id", None) != filter_id:
            return

        ts = format_ts(msg.date)
        is_self = msg.out or msg.sender_id == me_id

        if is_self:
            sender_text = Text("You", style=f"bold {p['self_msg']}")
        else:
            sender_name = "Unknown"
            if event.sender:
                sender_name = entity_name(event.sender)
            sender_text = Text(sender_name, style=f"bold {p['other_msg']}")

        chat_name = ""
        try:
            chat = await event.get_chat()
            chat_name = entity_name(chat)
        except Exception:
            pass

        # Media description
        content = msg.text or ""
        if not content and msg.media:
            media_type = type(msg.media).__name__.replace("MessageMedia", "")
            try:
                if hasattr(msg.media, "document"):
                    doc = msg.media.document
                    for attr in doc.attributes:
                        fname = getattr(attr, "file_name", None)
                        if fname:
                            size_mb = doc.size / 1_048_576
                            content = f"[{media_type}: {fname} {size_mb:.1f}MB]"
                            break
            except Exception:
                pass
            if not content:
                content = f"[{media_type}]"

        line = Text()
        line.append(f"[{ts}] ", style=p["timestamp"])
        if chat_name and not filter_id:
            line.append(f"{chat_name} · ", style=f"italic {p['dim']}")
        line.append_text(sender_text)
        line.append(": ")
        line.append(content)

        console.print(line)
        log.debug("watch: message from %s in %s", sender_text.plain, chat_name)

    # Register in watch registry only (fix #6)
    tg.on_new_message(handler, incoming=True, registry="watch")
    if include_out or filter_id:
        tg.on_new_message(handler, incoming=False, registry="watch")

    try:
        # Fix #6: proper event-driven stop, not magic sleep
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        tg.remove_watch_handlers()  # Fix #6: only removes watch handlers
        console.print(f"\n[{p['dim']}]Stopped watching.[/]")
        log.info("watch command stopped")
