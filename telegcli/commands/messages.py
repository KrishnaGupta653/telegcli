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
    get_console, print_success, print_error, print_warning,
    render_messages, entity_name, format_ts, get_palette,
)
from telegcli.utils.resolver import resolve_entity
from telegcli.utils.editor import open_editor

log = logging.getLogger("telegcli.messages")

# Injected by app.py so commands can prompt the user asynchronously (fix #8)
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


# ── read ──────────────────────────────────────────────────────────────────────

async def cmd_read(args: list[str]) -> None:
    """
    read <chat> [count]
    read <chat> search <query>
    read <chat> from <username>
    read <chat> before <YYYY-MM-DD>
    read <chat> --json
    """
    if not args:
        print_error("Usage: read <chat> [count] | search <q> | before <date> | --json")
        return

    cfg = get_config()
    console = get_console()
    p = get_palette()

    limit = cfg.get("msg_limit", 50)
    search = None
    from_user = None
    before_date = None
    output_json = "--json" in args
    args = [a for a in args if a != "--json"]

    name_parts = [args[0]]
    i = 1
    while i < len(args):
        token = args[i].lower()
        if token == "search" and i + 1 < len(args):
            search = " ".join(args[i + 1:])
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
        kwargs = {}
        if before_date:
            # Convert to max_id by fetching one message at that date — simpler: use offset_date
            messages = []
            async for msg in tg.raw.iter_messages(
                entity,
                limit=limit,
                search=search,
                from_user=from_user,
                offset_date=before_date,
            ):
                messages.append(msg)
        else:
            messages = await tg.get_messages(
                entity,
                limit=limit,
                search=search,
                from_user=from_user,
            )

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
    if search:
        header += f" — search: [italic]{search}[/]"
    elif before_date:
        header += f" — before {before_date.date()}"
    else:
        header += f" — last {len(messages)} messages"

    console.print(Rule(header, style=p["separator"]))
    render_messages(messages, me_id, chat_name)

    if cfg.get("auto_read"):
        await tg.mark_read(entity, messages[0].id)


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
    """delete <chat> <msg_id> [msg_id2 …]  [--local]"""
    if len(args) < 2:
        print_error("Usage: delete <chat> <msg_id> [msg_id2 …] [--local]")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    revoke = "--local" not in args
    id_args = [a for a in args[1:] if a != "--local"]

    try:
        msg_ids = [int(x) for x in id_args]
    except ValueError:
        print_error("All message IDs must be integers.")
        return

    scope = "everywhere" if revoke else "locally"
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
    """
    if len(args) < 3:
        print_error("Usage: forward <from_chat> <msg_ids> <to_chat>")
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
