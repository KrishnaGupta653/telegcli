"""
telegcli.commands.chats
─────────────────────
Commands: list, info, search, gsearch, mute, unmute, archive, markread,
          stats, export, gallery, pins

Fixes applied:
  #17 — timezone normalization in stats (msg.date.astimezone())
  #18 — day-group separators in render; timestamp-based pagination
  #11 — export supports --format json|csv|txt|html + full history flag
  Feature F — gallery command (media index)
  Feature J — stats --json
  
New Features:
  Feature 2 — pins command (pinned messages browser) --json support
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich import box

from telegcli.core.client import tg
from telegcli.core.config import get_config
from telegcli.ui.theme import (
    get_console, print_success, print_error, print_warning,
    render_dialog_list, render_chat_info, entity_name,
    format_ts, get_palette,
)
from telegcli.utils.resolver import resolve_entity, dialog_cache

log = logging.getLogger("telegcli.chats")


# ── list ──────────────────────────────────────────────────────────────────────

async def cmd_list(args: list[str]) -> None:
    """list [count] [--preview]  — list recent dialogs. Feature 15: --preview shows link titles."""
    console = get_console()
    p = get_palette()

    limit = 25
    show_link_preview = "--preview" in args
    clean_args = [a for a in args if a != "--preview"]
    
    if clean_args:
        try:
            limit = int(clean_args[0])
        except ValueError:
            pass

    with console.status("[bold blue]Loading chats…[/]"):
        dialogs = await tg.get_dialogs(limit=limit)
    
    # Feature 15: Add link preview if requested
    if show_link_preview:
        for dialog in dialogs:
            try:
                messages = await tg.get_messages(dialog, limit=3)
                for msg in messages:
                    if msg.text and ("http://" in msg.text or "https://" in msg.text):
                        # Extract first URL
                        import re
                        urls = re.findall(r'https?://\S+', msg.text)
                        if urls:
                            # Store link info in dialog for rendering
                            dialog.link_preview = urls[0]
                        break
            except Exception:
                pass

    dialog_cache.update(dialogs)
    table = render_dialog_list(dialogs)
    console.print(table)
    console.print(f"[{p['dim']}]  {len(dialogs)} chats loaded[/]")
    
    if show_link_preview:
        console.print(f"[{p['info']}]💡 URLs shown in first 3 messages of each chat[/]")


# ── info ──────────────────────────────────────────────────────────────────────

async def cmd_info(args: list[str]) -> None:
    """info <chat>  — detailed info about a chat or user."""
    if not args:
        print_error("Usage: info <chat>")
        return
    entity = await resolve_entity(args[0])
    if entity is None:
        return
    console = get_console()
    with console.status("[bold blue]Fetching info…[/]"):
        info = await tg.get_chat_info(entity)
    console.print(render_chat_info(info))


# ── search ────────────────────────────────────────────────────────────────────

async def cmd_search_chats(args: list[str]) -> None:
    """search <query>  — search across cached dialogs."""
    if not args:
        print_error("Usage: search <query>")
        return
    query = " ".join(args)
    console = get_console()
    p = get_palette()
    with console.status("[bold blue]Searching…[/]"):
        results = await tg.search_dialogs(query)
    if not results:
        print_warning(f"No chats found matching '{query}'.")
        return
    console.print(Rule(f"[{p['accent']}]Results for: {query}[/]", style=p["separator"]))
    console.print(render_dialog_list(results))


async def cmd_gsearch(args: list[str]) -> None:
    """gsearch <query>  — global message search across Telegram."""
    if not args:
        print_error("Usage: gsearch <query>")
        return
    query = " ".join(args)
    console = get_console()
    p = get_palette()
    with console.status("[bold blue]Searching globally…[/]"):
        messages = await tg.search_messages_global(query, limit=20)
    if not messages:
        print_warning(f"No messages found for '{query}'.")
        return
    console.print(Rule(f"[{p['accent']}]Global search: {query}[/]", style=p["separator"]))
    for msg in messages:
        ts = format_ts(getattr(msg, "date", None))
        text = getattr(msg, "text", "") or "[media]"
        console.print(
            f"  [{p['dim']}]{ts}[/]  [{p['accent']}]#{msg.id}[/]  "
            f"[{p['other_msg']}]{text[:80]}[/]"
        )


# ── mute / unmute / archive / markread ───────────────────────────────────────

async def cmd_mute(args: list[str]) -> None:
    if not args:
        print_error("Usage: mute <chat>")
        return
    entity = await resolve_entity(args[0])
    if entity is None:
        return
    await tg.mute_chat(entity)
    print_success(f"Muted {entity_name(entity)}")


async def cmd_unmute(args: list[str]) -> None:
    if not args:
        print_error("Usage: unmute <chat>")
        return
    entity = await resolve_entity(args[0])
    if entity is None:
        return
    await tg.unmute_chat(entity)
    print_success(f"Unmuted {entity_name(entity)}")


async def cmd_archive(args: list[str]) -> None:
    if not args:
        print_error("Usage: archive <chat>")
        return
    entity = await resolve_entity(args[0])
    if entity is None:
        return
    await tg.archive_chat(entity)
    print_success(f"Archived {entity_name(entity)}")


async def cmd_markread(args: list[str]) -> None:
    if not args:
        print_error("Usage: markread <chat>")
        return
    entity = await resolve_entity(args[0])
    if entity is None:
        return
    await tg.mark_read(entity)
    print_success(f"Marked {entity_name(entity)} as read.")


# ── stats ─────────────────────────────────────────────────────────────────────

async def cmd_stats(args: list[str]) -> None:
    """stats <chat> [count] [--json]"""
    if not args:
        print_error("Usage: stats <chat> [count] [--json]")
        return

    output_json = "--json" in args
    args = [a for a in args if a != "--json"]

    limit = 500
    if len(args) >= 2:
        try:
            limit = int(args[1])
        except ValueError:
            pass

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    console = get_console()
    p = get_palette()

    with console.status(f"[bold blue]Analysing last {limit} messages…[/]"):
        messages = await tg.get_messages(entity, limit=limit)

    if not messages:
        print_warning("No messages found.")
        return

    sender_count: Counter = Counter()
    sender_words: Counter = Counter()
    media_count: Counter = Counter()
    hour_count:  Counter = Counter()
    total_chars = 0

    for msg in messages:
        sender = "Unknown"
        if msg.sender:
            sender = entity_name(msg.sender)
        elif msg.out:
            sender = "You"

        sender_count[sender] += 1
        if msg.text:
            words = len(msg.text.split())
            sender_words[sender] += words
            total_chars += len(msg.text)
        if msg.media:
            media_type = type(msg.media).__name__.replace("MessageMedia", "")
            media_count[media_type] += 1
        if msg.date:
            # Fix #17: normalize to local timezone before extracting hour
            local_dt = msg.date.astimezone()
            hour_count[local_dt.hour] += 1

    if output_json:
        print(json.dumps({
            "total_messages": len(messages),
            "total_chars":    total_chars,
            "senders":        [
                {"name": s, "messages": c, "words": sender_words[s]}
                for s, c in sender_count.most_common()
            ],
            "media":          dict(media_count),
            "hourly_activity": {str(h): hour_count.get(h, 0) for h in range(24)},
        }, indent=2))
        return

    chat_name = entity_name(entity)
    console.print(Rule(f"[{p['accent']}]Stats: {chat_name}[/]", style=p["separator"]))
    console.print(f"  [{p['dim']}]Analysed {len(messages)} messages  ·  {total_chars:,} chars[/]\n")

    table = Table(
        title="Top Senders", box=box.SIMPLE, show_header=True,
        header_style=f"bold {p['accent']}",
    )
    table.add_column("Sender",        style=p["fg"])
    table.add_column("Messages",      style=p["accent"],  justify="right")
    table.add_column("Words",         style=p["accent2"], justify="right")
    table.add_column("Avg words/msg", justify="right",    style=p["dim"])

    for sender, count in sender_count.most_common(10):
        words = sender_words[sender]
        avg = f"{words / count:.1f}" if count else "0"
        table.add_row(sender, str(count), str(words), avg)
    console.print(table)

    if media_count:
        console.print()
        mt = Table(title="Media", box=box.SIMPLE, header_style=f"bold {p['accent']}")
        mt.add_column("Type",  style=p["fg"])
        mt.add_column("Count", style=p["accent2"], justify="right")
        for mtype, cnt in media_count.most_common():
            mt.add_row(mtype, str(cnt))
        console.print(mt)

    if hour_count:
        console.print()
        tz_name = datetime.now().astimezone().tzname() or "local"
        console.print(f"  [{p['accent']}]Activity by hour ({tz_name})[/]")
        peak = max(hour_count.values())
        for h in range(24):
            count = hour_count.get(h, 0)
            bar_len = int(count / peak * 30) if peak else 0
            bar = "█" * bar_len
            console.print(
                f"  [{p['dim']}]{h:02d}[/]  [{p['accent']}]{bar:<30}[/]  [{p['dim']}]{count}[/]"
            )


# ── export — fix #11 ──────────────────────────────────────────────────────────

async def cmd_export(args: list[str]) -> None:
    """
    export <chat> [count] [--format json|csv|txt|html] [--all]

    --all:   export entire chat history (paginated)
    Fix #11: multiple formats; full history option
    """
    if not args:
        print_error("Usage: export <chat> [count] [--format json|csv|txt|html] [--all]")
        return

    export_all = "--all" in args
    fmt_idx = next((i for i, a in enumerate(args) if a == "--format"), None)
    fmt = "json"
    clean_args = [a for a in args if a not in ("--all",)]

    if fmt_idx is not None and fmt_idx + 1 < len(args):
        fmt = args[fmt_idx + 1].lower()
        clean_args = [a for a in clean_args if a not in ("--format", fmt)]

    if fmt not in ("json", "csv", "txt", "html"):
        print_error("--format must be one of: json csv txt html")
        return

    limit = 200
    name_args = [clean_args[0]]
    for a in clean_args[1:]:
        if a.isdigit():
            limit = int(a)
        else:
            name_args.append(a)

    entity = await resolve_entity(" ".join(name_args))
    if entity is None:
        return

    console = get_console()

    if export_all:
        console.print("[bold blue]Exporting full chat history…[/] (this may take a while)")
        messages = []
        async for msg in tg.raw.iter_messages(entity):
            messages.append(msg)
    else:
        with console.status(f"[bold blue]Exporting {limit} messages…[/]"):
            messages = await tg.get_messages(entity, limit=limit)

    if not messages:
        print_warning("No messages to export.")
        return

    cfg = get_config()
    chat_name = entity_name(entity)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in chat_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = cfg.download_dir / f"{safe_name}_{timestamp}.{fmt}"

    export_data = [
        {
            "id":        msg.id,
            "date":      msg.date.isoformat() if msg.date else None,
            "sender_id": msg.sender_id,
            "sender":    entity_name(msg.sender) if msg.sender else ("You" if msg.out else "Unknown"),
            "out":       msg.out,
            "text":      msg.text or "",
            "media":     type(msg.media).__name__ if msg.media else None,
            "reply_to":  msg.reply_to_msg_id,
            "edit_date": msg.edit_date.isoformat() if msg.edit_date else None,
        }
        for msg in reversed(messages)
    ]

    if fmt == "json":
        content = json.dumps({"chat": chat_name, "messages": export_data},
                             indent=2, ensure_ascii=False)
    elif fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=export_data[0].keys())
        writer.writeheader()
        writer.writerows(export_data)
        content = buf.getvalue()
    elif fmt == "txt":
        lines = []
        for m in export_data:
            sender = m["sender"] or ("You" if m["out"] else "Unknown")
            lines.append(f"[{m['date']}] {sender}: {m['text']}")
        content = "\n".join(lines)
    elif fmt == "html":
        rows = "\n".join(
            f"<tr><td>{m['date']}</td><td>{m['sender']}</td>"
            f"<td>{m['text'].replace('<','&lt;')}</td></tr>"
            for m in export_data
        )
        content = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{chat_name}</title></head><body>"
            f"<h1>{chat_name}</h1><table border='1'>"
            "<tr><th>Date</th><th>Sender</th><th>Message</th></tr>"
            f"{rows}</table></body></html>"
        )

    out_path.write_text(content, encoding="utf-8")
    print_success(
        f"Exported {len(export_data)} messages → {out_path}  [{fmt.upper()}]"
    )


# ── pins — Feature 2: Pinned messages browser ─────────────────────────────────

async def cmd_pins(args: list[str]) -> None:
    """
    pins <chat>         — show all pinned messages
    pins <chat> --json  — JSON output for parsing
    pins <chat> [limit] — show last N pinned messages (default 20)
    
    Feature 2: Pinned messages browser
    """
    if not args:
        print_error("Usage: pins <chat> [limit] [--json]")
        return
    
    console = get_console()
    p = get_palette()
    
    limit = 20
    output_json = "--json" in args
    
    # Parse arguments
    entity_query = args[0]
    for arg in args[1:]:
        if arg == "--json":
            continue
        elif arg.isdigit():
            limit = int(arg)
    
    entity = await resolve_entity(entity_query)
    if entity is None:
        return
    
    with console.status("[bold blue]Loading pinned messages…[/]"):
        try:
            # Fetch pinned messages (Telethon provides this via get_messages with search=None but pinned filter)
            # Alternative: use raw TL API if needed
            pinned_messages = []
            async for msg in tg.raw.iter_messages(entity, search=None):
                if msg.pinned:
                    pinned_messages.append(msg)
                if len(pinned_messages) >= limit:
                    break
        except Exception as e:
            log.warning("Could not fetch pinned messages: %s", e)
            print_error(f"Could not load pinned messages: {e}")
            return
    
    if not pinned_messages:
        print_warning("No pinned messages in this chat.")
        return
    
    chat_name = entity_name(entity)
    me_id = tg.me.id if tg.me else 0
    
    # JSON output
    if output_json:
        data = [
            {
                "id": msg.id,
                "date": msg.date.isoformat() if msg.date else None,
                "sender_id": msg.sender_id,
                "text": msg.text or "",
                "media": type(msg.media).__name__ if msg.media else None,
                "edit_date": msg.edit_date.isoformat() if msg.edit_date else None,
            }
            for msg in reversed(pinned_messages)
        ]
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return
    
    # Regular output
    console.print(
        Rule(f"[{p['accent']}]{chat_name}[/] — [bold]Pinned messages[/]", style=p["separator"])
    )
    
    from telegcli.ui.theme import render_messages
    render_messages(pinned_messages, me_id, chat_name)
    console.print(f"[{p['dim']}]  {len(pinned_messages)} pinned message(s)[/]")
    log.info("Exported %d messages to %s", len(export_data), out_path)


# ── gallery — Feature F ───────────────────────────────────────────────────────

async def cmd_gallery(args: list[str]) -> None:
    """
    gallery <chat> [count]
    List all media messages with type, size, filename, and message ID.
    """
    if not args:
        print_error("Usage: gallery <chat> [count]")
        return

    limit = 100
    if len(args) >= 2:
        try:
            limit = int(args[1])
        except ValueError:
            pass

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    console = get_console()
    p = get_palette()

    with console.status("[bold blue]Loading media…[/]"):
        messages = []
        async for msg in tg.raw.iter_messages(entity, limit=limit, filter="InputMessagesFilterEmpty"):
            if msg.media:
                messages.append(msg)

    if not messages:
        print_warning("No media found.")
        return

    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

    chat_name = entity_name(entity)
    console.print(Rule(f"[{p['accent']}]Gallery: {chat_name}[/]", style=p["separator"]))

    table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}", show_header=True)
    table.add_column("#",    style=p["dim"],  width=5)
    table.add_column("ID",   style=p["accent"], width=8)
    table.add_column("Type", style=p["fg"],   width=12)
    table.add_column("Name", style=p["fg"],   ratio=3)
    table.add_column("Size", style=p["dim"],  width=10, justify="right")
    table.add_column("Date", style=p["timestamp"], width=12)

    for i, msg in enumerate(reversed(messages)):
        media_type = type(msg.media).__name__.replace("MessageMedia", "")
        name = ""
        size_str = ""

        if isinstance(msg.media, MessageMediaDocument) and msg.media.document:
            doc = msg.media.document
            size_str = _fmt_size(doc.size)
            for attr in doc.attributes:
                fname = getattr(attr, "file_name", None)
                if fname:
                    name = fname
                    break
        elif isinstance(msg.media, MessageMediaPhoto):
            name = "(photo)"

        ts = format_ts(msg.date)
        table.add_row(str(i + 1), f"#{msg.id}", media_type, name, size_str, ts)

    console.print(table)
    console.print(f"[{p['dim']}]  {len(messages)} media items  ·  download with: download <chat> <msg_id>[/]")


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"
