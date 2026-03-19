"""
telegcli.commands.messages
────────────────────────
Commands: read, send, reply, edit, delete, forward, react, pin, unpin,
          copy, thread

Fixes applied:
  #7  — paginated read via iter_messages; date-group separators; --before flag
  #8  — all input prompts use repl.prompt_async() (async, non-blocking)
  #12 — copy command implemented using pyperclip
  #17 — timezone normalization for stats (in chats.py)
  #18 — day separators in render_messages; --before pagination flag
  Feature C — thread view
  Feature J — --json output flag
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import pyperclip
from rich.text import Text
from rich.rule import Rule

from telegcli.core.client import tg
from telegcli.core.config import get_config
from telegcli.ui.theme import (
    get_console, print_success, print_error, print_warning, print_info,
    render_messages, entity_name, format_ts, get_palette,
)
from telegcli.utils.media_preview import is_image_message, render_message_image_preview
from telegcli.utils.resolver import resolve_entity
from telegcli.utils.editor import open_editor

log = logging.getLogger("telegcli.messages")

# Injected by app.py so commands can prompt the user asynchronously (fix #8)
# Note: This is for backwards compatibility; new code should use _repl from telegcli.ui.repl
_repl: Optional[object] = None


def set_repl(repl) -> None:
    global _repl
    _repl = repl


async def _ask(prompt: str) -> str:
    """Async prompt via REPL session. Fix #8."""
    if _repl is not None:
        return await _repl.prompt_async(prompt)
    # Fallback for contexts without REPL (tests etc.)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input, f"{prompt} ")


async def _confirm(prompt: str) -> bool:
    """Async yes/no prompt. Fix #8."""
    ans = await _ask(f"{prompt} [y/N]:")
    return ans.strip().lower() in ("y", "yes")


def _filter_messages_by_type(messages: list, msg_type: str) -> list:
    """Filter messages by media type. Feature 3: Advanced filtering."""
    filtered = []
    for msg in messages:
        if msg_type == "photo" and getattr(msg, "photo", None):
            filtered.append(msg)
        elif msg_type == "video" and getattr(msg, "video", None):
            filtered.append(msg)
        elif msg_type == "document" and getattr(msg, "document", None):
            filtered.append(msg)
        elif msg_type == "voice" and getattr(msg, "voice", None):
            filtered.append(msg)
        elif msg_type == "audio" and getattr(msg, "audio", None):
            filtered.append(msg)
        elif msg_type == "video_note" and getattr(msg, "video_note", None):
            filtered.append(msg)
        elif msg_type == "animation" and getattr(msg, "animation", None):
            filtered.append(msg)
        elif msg_type == "link" and msg.text and ("http://" in msg.text or "https://" in msg.text):
            filtered.append(msg)
    return filtered


# ── read ──────────────────────────────────────────────────────────────────────

async def cmd_read(args: list[str]) -> None:
    """
    read <chat> [count]
    read <chat> search <query>
    read <chat> from <username>
    read <chat> before <YYYY-MM-DD>
    read <chat> --first-unread      [Feature 1: Jump to first unread]
    read <chat> --type photo|video|document|link|voice|video_note
    read <chat> --since <YYYY-MM-DD>
    read <chat> --until <YYYY-MM-DD>
    read <chat> --json
    """
    if not args:
        print_error("Usage: read <chat> [count] | search <q> | before <date> | --first-unread | --type <type> | --since/--until <date> | --json")
        return

    cfg = get_config()
    console = get_console()
    p = get_palette()

    limit = cfg.get("msg_limit", 50)
    search = None
    from_user = None
    before_date = None
    since_date = None
    until_date = None
    msg_type = None
    first_unread = "--first-unread" in args
    output_json = "--json" in args
    args = [a for a in args if a not in ("--json", "--first-unread")]

    name_parts = [args[0]]
    i = 1
    while i < len(args):
        token = args[i].lower()
        if token == "search" and i + 1 < len(args):
            search = " ".join(args[i + 1:])
            # Validate search query
            if search and len(search.strip()) < 2:
                print_error("Search query must be at least 2 characters")
                return
            break
        elif token == "from" and i + 1 < len(args):
            from_user = args[i + 1]
            i += 2
        elif token == "before" and i + 1 < len(args):
            try:
                before_date = datetime.strptime(args[i + 1], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                i += 2
            except ValueError:
                print_error("before date format: YYYY-MM-DD")
                return
        elif token == "--since" and i + 1 < len(args):
            try:
                since_date = datetime.strptime(args[i + 1], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                i += 2
            except ValueError:
                print_error("--since date format: YYYY-MM-DD")
                return
        elif token == "--until" and i + 1 < len(args):
            try:
                until_date = datetime.strptime(args[i + 1], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                i += 2
            except ValueError:
                print_error("--until date format: YYYY-MM-DD")
                return
        elif token == "--type" and i + 1 < len(args):
            msg_type = args[i + 1].lower()
            valid_types = ("photo", "video", "document", "link", "voice", "video_note", "audio", "animation")
            if msg_type not in valid_types:
                print_error(f"--type must be one of: {', '.join(valid_types)}")
                return
            i += 2
        elif args[i].isdigit():
            limit = int(args[i])
            i += 1
        else:
            name_parts.append(args[i])
            i += 1

    query = " ".join(name_parts)
    entity = await resolve_entity(query)
    if entity is None:
        return

    with console.status("[bold blue]Loading messages…[/]"):
        # Feature 1: First unread jump
        if first_unread:
            try:
                # Get chat to check unread count
                chat = await tg.get_chat_info(entity)
                unread_count = getattr(chat, 'unread_count', 0)
                if unread_count == 0:
                    print_info("No unread messages.")
                    return
                # Load from a reasonable offset before first unread
                messages = await tg.get_messages(
                    entity,
                    limit=max(50, min(100, unread_count + 20)),  # Get extra context
                )
                # Filter to show last messages (which will include unread)
                messages = messages[-min(50, unread_count + 10):]
            except Exception as e:
                log.warning("Could not get unread count: %s. Falling back to normal read.", e)
                messages = await tg.get_messages(entity, limit=limit)
        else:
            kwargs = {}
            if search:
                messages = []
                async for msg in tg.raw.iter_messages(
                    entity,
                    limit=limit,
                    search=search,
                    from_user=from_user,
                ):
                    messages.append(msg)
            elif before_date or since_date or until_date:
                messages = []
                async for msg in tg.raw.iter_messages(entity, limit=limit):
                    msg_dt = msg.date.replace(tzinfo=timezone.utc) if msg.date else None
                    if before_date and msg_dt and msg_dt > before_date:
                        continue
                    if since_date and msg_dt and msg_dt < since_date:
                        continue
                    if until_date and msg_dt and msg_dt > until_date:
                        continue
                    messages.append(msg)
            else:
                messages = await tg.get_messages(
                    entity,
                    limit=limit,
                    search=search,
                    from_user=from_user,
                )

        # Feature 3: Type filtering
        if msg_type:
            messages = _filter_messages_by_type(messages, msg_type)

    if not messages:
        print_warning("No messages found.")
        return

    me_id = tg.me.id if tg.me else 0
    chat_name = entity_name(entity)

    # Feature J: JSON output
    if output_json:
        data = [_msg_to_dict(m) for m in reversed(messages)]
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return

    header = f"[{p['accent']}]{chat_name}[/]"
    extra_filters = []
    if search:
        extra_filters.append(f"search: [italic]{search}[/]")
    if msg_type:
        extra_filters.append(f"type: [italic]{msg_type}[/]")
    if before_date:
        extra_filters.append(f"before {before_date.date()}")
    if since_date:
        extra_filters.append(f"since {since_date.date()}")
    if until_date:
        extra_filters.append(f"until {until_date.date()}")
    if first_unread:
        extra_filters.append("[bold]first unread[/]")
    
    if extra_filters:
        header += f" — {' | '.join(extra_filters)}"
    else:
        header += f" — last {len(messages)} messages"

    console.print(Rule(header, style=p["separator"]))
    render_messages(messages, me_id, chat_name)

    # Optional inline image previews for terminal-friendly media browsing.
    if cfg.get("image_preview", True):
        await _render_inline_previews(messages, cfg)

    if cfg.get("auto_read"):
        await tg.mark_read(entity, messages[0].id)


def _is_photo_message(msg) -> bool:
    return getattr(msg, "photo", None) is not None


async def _render_inline_previews(messages: list, cfg) -> None:
    console = get_console()
    p = get_palette()

    ordered = list(reversed(messages))
    image_msgs = [m for m in ordered if is_image_message(m)]
    if cfg.get("image_preview_photos_only", False):
        image_msgs = [m for m in image_msgs if _is_photo_message(m)]

    if not image_msgs:
        return

    max_previews = cfg.get("image_preview_max", 3)
    preview_width = cfg.get("image_preview_width", 56)

    if max_previews <= 0:
        return

    console.print(Rule(f"[{p['dim']}]Image previews[/]", style=p["separator"]))

    shown = 0
    for msg in image_msgs:
        if shown >= max_previews:
            break
        preview = await render_message_image_preview(tg.raw, msg, width=preview_width)
        if not preview:
            continue

        console.print(f"[{p['dim']}]# {msg.id}[/]")
        console.print(preview)
        console.print()
        shown += 1

    skipped = max(0, len(image_msgs) - shown)
    if skipped:
        console.print(f"[{p['dim']}]... {skipped} more image(s) not shown in preview.[/]")


def _msg_to_dict(msg) -> dict:
    return {
        "id":        msg.id,
        "date":      msg.date.isoformat() if msg.date else None,
        "sender_id": msg.sender_id,
        "out":       msg.out,
        "text":      msg.text or "",
        "media":     type(msg.media).__name__ if msg.media else None,
        "reply_to":  msg.reply_to_msg_id,
        "edit_date": msg.edit_date.isoformat() if msg.edit_date else None,
    }


# ── send ──────────────────────────────────────────────────────────────────────

async def cmd_send(args: list[str]) -> None:
    """
    send <chat>              → async prompt for message
    send <chat> <message>    → sends inline
    send <chat> --template <name>  → use saved template (Feature G)
    """
    if not args:
        print_error("Usage: send <chat> [message text]")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    cfg = get_config()
    console = get_console()
    p = get_palette()

    # Template shortcut (Feature G)
    if len(args) >= 3 and args[1] == "--template":
        tmpl_name = args[2]
        templates = cfg.get("templates", {})
        text = templates.get(tmpl_name)
        if not text:
            print_error(f"Template '{tmpl_name}' not found. Use: template list")
            return
    elif len(args) > 1:
        text = " ".join(args[1:])
    else:
        console.print(
            f"[{p['dim']}]Composing to[/] [{p['accent']}]{entity_name(entity)}[/]"
            f"  [{p['dim']}](Enter to send, Ctrl+C to cancel, \\e for editor)[/]"
        )
        text = await _ask(">")
        if text == r"\e":
            text = await open_editor()

    if not text or not text.strip():
        print_warning("Empty message — not sent.")
        return

    msg = await tg.send_message(entity, text.strip())
    print_success(f"Sent  #{msg.id}  to {entity_name(entity)}")
    log.info("Sent message #%d to %s", msg.id, entity_name(entity))


# ── reply ─────────────────────────────────────────────────────────────────────

async def cmd_reply(args: list[str]) -> None:
    """reply <chat> <msg_id> [text]"""
    if len(args) < 2:
        print_error("Usage: reply <chat> <msg_id> [text]")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    try:
        reply_to = int(args[1])
    except ValueError:
        print_error("msg_id must be an integer.")
        return

    p = get_palette()
    if len(args) > 2:
        text = " ".join(args[2:])
    else:
        get_console().print(
            f"[{p['dim']}]Replying to[/] [{p['accent']}]#{reply_to}[/]"
            f"  [{p['dim']}](Ctrl+C to cancel)[/]"
        )
        text = await _ask(">")

    if not text.strip():
        print_warning("Empty message — not sent.")
        return

    msg = await tg.send_message(entity, text.strip(), reply_to=reply_to)
    print_success(f"Reply sent  #{msg.id}")


# ── edit ──────────────────────────────────────────────────────────────────────

async def cmd_edit(args: list[str]) -> None:
    """edit <chat> <msg_id> [new text]"""
    if len(args) < 2:
        print_error("Usage: edit <chat> <msg_id> [new text]")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    try:
        msg_id = int(args[1])
    except ValueError:
        print_error("msg_id must be an integer.")
        return

    if len(args) > 2:
        new_text = " ".join(args[2:])
    else:
        console = get_console()
        p = get_palette()
        try:
            target = await tg.raw.get_messages(entity, ids=msg_id)
            if target and target.text:
                console.print(f"[{p['dim']}]Original: {target.text}[/]")
        except Exception:
            pass
        console.print(f"[{p['dim']}]New text (Ctrl+C to cancel):[/]")
        new_text = await _ask(">")

    if not new_text.strip():
        print_warning("Empty text — not edited.")
        return

    await tg.edit_message(entity, msg_id, new_text.strip())
    print_success(f"Message #{msg_id} edited.")


# ── delete ────────────────────────────────────────────────────────────────────

async def cmd_delete(args: list[str]) -> None:
    """
    delete <chat> <msg_id> [msg_id2 …]  [--local] [--force]
    
    Feature 4: Delete confirmation with --force to skip
    """
    if len(args) < 2:
        print_error("Usage: delete <chat> <msg_id> [msg_id2 …] [--local] [--force]")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    revoke = "--local" not in args
    force_delete = "--force" in args
    id_args = [a for a in args[1:] if a not in ("--local", "--force")]

    # Feature 7: Support for range deletion (e.g., "10-20")
    try:
        msg_ids = []
        for x in id_args:
            if "-" in x and not x.startswith("-"):  # Range like "10-20"
                parts = x.split("-")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    start, end = int(parts[0]), int(parts[1])
                    msg_ids.extend(range(start, end + 1))
                else:
                    print_error(f"Invalid range format: {x}. Use format: 10-20")
                    return
            else:
                msg_ids.append(int(x))
    except ValueError:
        print_error("All message IDs must be integers (or ranges like 10-20).")
        return

    # Remove duplicates while preserving order
    msg_ids = list(dict.fromkeys(msg_ids))

    scope = "everywhere" if revoke else "locally"
    
    if not force_delete:
        confirmed = await _confirm(
            f"Delete {len(msg_ids)} message(s) {scope}?"
        )
        if not confirmed:
            print_warning("Cancelled.")
            return

    await tg.delete_messages(entity, msg_ids, revoke=revoke)
    print_success(f"Deleted {len(msg_ids)} message(s).")
    log.info("Deleted messages %s from %s", msg_ids, entity_name(entity))


# ── forward ───────────────────────────────────────────────────────────────────

async def cmd_forward(args: list[str]) -> None:
    """
    forward <from_chat> <msg_id> <to_chat>
    forward <from_chat> <msg_id1,msg_id2,...> <to_chat>   (bulk, Feature H)
    forward <from_chat> <msg_id> <to_chat> --edit         (Feature 12: edit caption)
    """
    if len(args) < 3:
        print_error("Usage: forward <from_chat> <msg_ids> <to_chat> [--edit]")
        return

    from_entity = await resolve_entity(args[0])
    if from_entity is None:
        return

    # Support comma-separated IDs for bulk forward (Feature H)
    try:
        msg_ids = [int(x.strip()) for x in args[1].split(",")]
    except ValueError:
        print_error("msg_id must be integers (comma-separated for multiple).")
        return

    to_entity = await resolve_entity(args[2])
    if to_entity is None:
        return
    
    # Feature 12: Support --edit flag to edit caption before forwarding
    edit_mode = "--edit" in args
    
    if edit_mode and len(msg_ids) == 1:
        # Get the message to show caption
        messages = await tg.get_messages(from_entity, ids=[msg_ids[0]])
        if messages:
            msg = messages[0]
            old_caption = msg.text or "(no caption)"
            console.print(f"[{p['info']}]Current caption: {old_caption}[/]")
            
            # Edit caption via _ask helper (already properly imported)
            try:
                new_caption = await _ask(
                    "[{p['accent']}]New caption (or leave blank to keep)[/]:"
                )
                if new_caption:
                    # Forward and edit the forwarded message
                    await tg.forward_messages(from_entity, to_entity, msg_ids)
                    # Get the forwarded message and edit it
                    forwarded = await tg.get_messages(to_entity, limit=1)
                    if forwarded:
                        await tg.edit_message(to_entity, forwarded[0].id, text=new_caption)
                        print_success(f"Forwarded and edited caption for {len(msg_ids)} message(s)")
                else:
                    await tg.forward_messages(from_entity, to_entity, msg_ids)
                    print_success(f"Forwarded {len(msg_ids)} message(s)")
            except Exception as e:
                print_warning(f"Could not edit caption: {e}")
                await tg.forward_messages(from_entity, to_entity, msg_ids)
    else:
        await tg.forward_messages(from_entity, to_entity, msg_ids)
    
    print_success(
        f"Forwarded {len(msg_ids)} message(s) "
        f"from {entity_name(from_entity)} → {entity_name(to_entity)}"
    )


# ── react ─────────────────────────────────────────────────────────────────────

COMMON_REACTIONS = ["👍", "❤️", "🔥", "🎉", "😂", "😮", "😢", "👎", "💯", "🤔"]


async def cmd_react(args: list[str]) -> None:
    """react <chat> <msg_id> [emoji]"""
    if len(args) < 2:
        print_error("Usage: react <chat> <msg_id> [emoji]")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    try:
        msg_id = int(args[1])
    except ValueError:
        print_error("msg_id must be an integer.")
        return

    if len(args) >= 3:
        emoji = args[2]
    else:
        console = get_console()
        p = get_palette()
        console.print(f"[{p['dim']}]Common reactions:[/]")
        for i, r in enumerate(COMMON_REACTIONS):
            console.print(f"  [{p['accent']}]{i+1}[/]  {r}")
        choice = await _ask("Emoji or number:")
        choice = choice.strip()
        if choice.isdigit() and 1 <= int(choice) <= len(COMMON_REACTIONS):
            emoji = COMMON_REACTIONS[int(choice) - 1]
        else:
            emoji = choice

    await tg.send_reaction(entity, msg_id, emoji)
    print_success(f"Reacted {emoji} to #{msg_id}")


# ── pin / unpin ───────────────────────────────────────────────────────────────

async def cmd_pin(args: list[str]) -> None:
    """pin <chat> <msg_id> [--notify]"""
    if len(args) < 2:
        print_error("Usage: pin <chat> <msg_id> [--notify]")
        return
    entity = await resolve_entity(args[0])
    if entity is None:
        return
    try:
        msg_id = int(args[1])
    except ValueError:
        print_error("msg_id must be an integer.")
        return
    notify = "--notify" in args
    await tg.pin_message(entity, msg_id, notify=notify)
    print_success(f"Pinned #{msg_id}")


async def cmd_unpin(args: list[str]) -> None:
    """unpin <chat> <msg_id>"""
    if len(args) < 2:
        print_error("Usage: unpin <chat> <msg_id>")
        return
    entity = await resolve_entity(args[0])
    if entity is None:
        return
    try:
        msg_id = int(args[1])
    except ValueError:
        print_error("msg_id must be an integer.")
        return
    await tg.unpin_message(entity, msg_id)
    print_success(f"Unpinned #{msg_id}")


# ── copy — Feature + fix #12 ──────────────────────────────────────────────────

async def cmd_copy(args: list[str]) -> None:
    """copy <chat> <msg_id>  — copy message text to system clipboard"""
    if len(args) < 2:
        print_error("Usage: copy <chat> <msg_id>")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    try:
        msg_id = int(args[1])
    except ValueError:
        print_error("msg_id must be an integer.")
        return

    try:
        msg = await tg.raw.get_messages(entity, ids=msg_id)
    except Exception as e:
        print_error(f"Could not fetch message #{msg_id}: {e}")
        return

    if msg is None:
        print_error(f"Message #{msg_id} not found.")
        return

    text = msg.text or ""
    if not text:
        print_warning(f"Message #{msg_id} has no text to copy.")
        return

    try:
        pyperclip.copy(text)
        print_success(f"Copied #{msg_id} ({len(text)} chars) to clipboard.")
    except pyperclip.PyperclipException as e:
        print_error(f"Clipboard unavailable: {e}\nText:\n{text}")


# ── thread — Feature C ────────────────────────────────────────────────────────

async def cmd_thread(args: list[str]) -> None:
    """thread <chat> <msg_id>  — show a message and all its replies"""
    if len(args) < 2:
        print_error("Usage: thread <chat> <msg_id>")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    try:
        msg_id = int(args[1])
    except ValueError:
        print_error("msg_id must be an integer.")
        return

    console = get_console()
    p = get_palette()

    with console.status("[bold blue]Loading thread…[/]"):
        # Fetch the root message
        try:
            root = await tg.raw.get_messages(entity, ids=msg_id)
        except Exception as e:
            print_error(f"Could not fetch message #{msg_id}: {e}")
            return

        # Fetch replies to this message
        replies = await tg.get_messages(entity, reply_to=msg_id, limit=100)

    me_id = tg.me.id if tg.me else 0
    chat_name = entity_name(entity)

    console.print(
        Rule(f"[{p['accent']}]Thread #{msg_id} in {chat_name}[/]", style=p["separator"])
    )

    if root:
        render_messages([root], me_id, chat_name)

    if replies:
        console.print(f"  [{p['dim']}]↳ {len(replies)} repl{'y' if len(replies)==1 else 'ies'}[/]\n")
        render_messages(list(reversed(replies)), me_id, chat_name)
    else:
        console.print(f"  [{p['dim']}]No replies.[/]")


async def cmd_preview(args: list[str]) -> None:
    """preview <chat> <msg_id> — render ASCII preview for a specific image message."""
    if len(args) < 2:
        print_error("Usage: preview <chat> <msg_id>")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    try:
        msg_id = int(args[1])
    except ValueError:
        print_error("msg_id must be an integer.")
        return

    console = get_console()
    p = get_palette()
    cfg = get_config()

    with console.status("[bold blue]Loading preview…[/]"):
        try:
            msg = await tg.raw.get_messages(entity, ids=msg_id)
        except Exception as e:
            print_error(f"Could not fetch message #{msg_id}: {e}")
            return

        if msg is None:
            print_error(f"Message #{msg_id} not found.")
            return

        if not is_image_message(msg):
            print_warning(f"Message #{msg_id} is not an image media message.")
            return

        preview = await render_message_image_preview(
            tg.raw,
            msg,
            width=cfg.get("image_preview_width", 56),
        )

    if not preview:
        print_warning(f"Could not render preview for #{msg_id}.")
        return

    console.print(Rule(f"[{p['accent']}]Preview #{msg_id}[/]", style=p["separator"]))
    console.print(preview)


# ── pins — Feature 2 ──────────────────────────────────────────────────────────

async def cmd_pins(args: list[str]) -> None:
    """
    pins <chat> [limit]        — show all pinned messages
    pins <chat> [limit] --json — output as JSON
    
    Feature 2: Pinned messages browser
    """
    if not args:
        print_error("Usage: pins <chat> [limit] [--json]")
        return

    limit = 50
    output_json = "--json" in args
    clean_args = [a for a in args if a != "--json"]

    if len(clean_args) > 1:
        try:
            limit = int(clean_args[1])
        except ValueError:
            limit = 50

    entity = await resolve_entity(clean_args[0])
    if entity is None:
        return

    console = get_console()
    p = get_palette()

    with console.status("[bold blue]Loading pinned messages…[/]"):
        try:
            # Use telethon's SearchRequest to filter pinned messages
            from telethon.functions.messages import SearchRequest
            from telethon.types import InputMessagesFilterPinned
            
            result = await tg.raw(SearchRequest(
                peer=entity,
                q="",  # Empty query to get all pinned
                filter=InputMessagesFilterPinned(),
                min_date=None,
                max_date=None,
                offset_id=0,
                add_offset=0,
                limit=limit,
                max_id=0,
                min_id=0,
                hash=0,
            ))
            pinned_messages = result.messages if hasattr(result, 'messages') else []
        except Exception as e:
            log.error("Error fetching pinned messages: %s", e)
            print_error(f"Could not fetch pinned messages: {e}")
            return

    if not pinned_messages:
        print_info("No pinned messages found.")
        return

    me_id = tg.me.id if tg.me else 0
    chat_name = entity_name(entity)

    # JSON output (Feature J: --json support)
    if output_json:
        data = [_msg_to_dict(m) for m in pinned_messages]
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return

    # Rich output
    console.print(
        Rule(f"[{p['accent']}]{chat_name}[/] — {len(pinned_messages)} pinned message(s)",
             style=p["separator"])
    )
    render_messages(list(reversed(pinned_messages)), me_id, chat_name)
