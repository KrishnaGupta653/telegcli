"""
telegcli.commands.misc
────────────────────
Commands: me, schedule, automate, template, draft, sessions,
          theme, config, logout, clear, help

Fixes applied:
  #8  — async prompts via repl._ask()
  #9  — sessions command for multi-account management
  #10 — automate remove <index> implemented; improved rule UX
  #16 — theme command refreshes REPL style immediately

New features:
  G — template system (save, use, list, delete)
  B — drafts system (save, list, send, delete)
  I — sessions management
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich import box

from telegcli.core.client import tg
from telegcli.core.config import get_config
from telegcli.ui.theme import (
    get_console, print_success, print_error, print_warning,
    print_info, get_palette, refresh_console,
)
from telegcli.utils.resolver import resolve_entity
from telegcli.ui.repl import COMMANDS
from telegcli.utils.automations import automation_engine

log = logging.getLogger("telegcli.misc")

_repl = None


def set_repl(repl) -> None:
    global _repl
    _repl = repl


async def _ask(prompt: str) -> str:
    if _repl is not None:
        return await _repl.prompt_async(prompt)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input, f"{prompt} ")


# ── me ────────────────────────────────────────────────────────────────────────

async def cmd_me(args: list[str]) -> None:
    """Show your Telegram account info."""
    console = get_console()
    p = get_palette()
    with console.status("[bold blue]Fetching account info…[/]"):
        me = await tg.raw.get_me()
    lines = [
        f"[{p['dim']}]{'Name':<14}[/] [{p['fg']}]{me.first_name or ''} {me.last_name or ''}[/]",
        f"[{p['dim']}]{'Username':<14}[/] [{p['accent']}]@{me.username or '(none)'}[/]",
        f"[{p['dim']}]{'Phone':<14}[/] [{p['fg']}]{me.phone or '(hidden)'}[/]",
        f"[{p['dim']}]{'ID':<14}[/] [{p['dim']}]{me.id}[/]",
        f"[{p['dim']}]{'Premium':<14}[/] [{p['accent2']}]{getattr(me, 'premium', False)}[/]",
        f"[{p['dim']}]{'Verified':<14}[/] [{p['success']}]{me.verified}[/]",
    ]
    console.print(Panel(
        "\n".join(lines),
        title=f"[{p['accent']}]Your Account[/]",
        border_style=p["separator"], padding=(1, 2),
    ))


# ── schedule ──────────────────────────────────────────────────────────────────

async def cmd_schedule(args: list[str]) -> None:
    """schedule <chat> <YYYY-MM-DD> [HH:MM] <text>"""
    if len(args) < 3:
        print_error("Usage: schedule <chat> <YYYY-MM-DD> [HH:MM] <text>")
        return

    entity = await resolve_entity(args[0])
    if entity is None:
        return

    schedule_dt: Optional[datetime] = None
    text_start = 2

    if len(args) >= 3:
        combined = f"{args[1]} {args[2]}"
        try:
            schedule_dt = datetime.strptime(combined, "%Y-%m-%d %H:%M")
            text_start = 3
        except ValueError:
            pass

    if schedule_dt is None:
        try:
            schedule_dt = datetime.strptime(args[1], "%Y-%m-%d")
        except ValueError:
            print_error("Date format: YYYY-MM-DD [HH:MM]  (e.g. 2025-12-25 09:00)")
            return

    text = " ".join(args[text_start:])
    if not text:
        print_error("Message text cannot be empty.")
        return

    msg = await tg.send_message(entity, text, schedule=schedule_dt)
    print_success(f"Scheduled #{msg.id} for {schedule_dt.strftime('%b %d %Y %H:%M')}")


# ── automate — fix #10 ────────────────────────────────────────────────────────

async def cmd_automate(args: list[str]) -> None:
    """
    automate list
    automate add <trigger> <reply>   [--private] [--chat @x] [--user @x] [--limit N]
    automate remove <index>
    automate enable <index>
    automate disable <index>
    automate clear
    """
    console = get_console()
    p = get_palette()
    cfg = get_config()
    sub = args[0].lower() if args else "list"

    if sub == "list":
        rules = cfg.get("automations", [])
        if not rules:
            print_info("No automations configured.")
            return
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}", show_header=True)
        table.add_column("#",        style=p["dim"],   width=4)
        table.add_column("Trigger",  style=p["fg"],    ratio=1)
        table.add_column("Reply",    style=p["accent2"], ratio=2)
        table.add_column("Filters",  style=p["dim"],   ratio=1)
        table.add_column("On",       width=4)
        for i, rule in enumerate(rules):
            filters = []
            if rule.get("only_private"):     filters.append("DM")
            if rule.get("chat_filter"):      filters.append(f"chat={rule['chat_filter']}")
            if rule.get("user_filter"):      filters.append(f"user={rule['user_filter']}")
            if rule.get("max_fires_per_hour"): filters.append(f"≤{rule['max_fires_per_hour']}/hr")
            enabled = "✓" if rule.get("enabled", True) else "✗"
            table.add_row(
                str(i + 1),
                rule.get("trigger", ""),
                rule.get("reply", ""),
                " ".join(filters) or "—",
                enabled,
            )
        console.print(table)

    elif sub == "add":
        # fix #10: positional args instead of raw JSON
        # automate add <trigger> <reply> [options]
        if len(args) < 3:
            print_error(
                "Usage: automate add <trigger> <reply> "
                "[--private] [--chat @x] [--user @x] [--limit N]"
            )
            return

        trigger = args[1]
        reply_parts = []
        options_start = 2
        for i, a in enumerate(args[2:], start=2):
            if a.startswith("--"):
                options_start = i
                break
            reply_parts.append(a)

        reply_text = " ".join(reply_parts)
        if not reply_text:
            print_error("Reply text cannot be empty.")
            return

        rule: dict = {"trigger": trigger, "reply": reply_text, "enabled": True}

        opts = args[options_start:]
        i = 0
        while i < len(opts):
            opt = opts[i]
            if opt == "--private":
                rule["only_private"] = True
            elif opt == "--chat" and i + 1 < len(opts):
                rule["chat_filter"] = opts[i + 1]; i += 1
            elif opt == "--user" and i + 1 < len(opts):
                rule["user_filter"] = opts[i + 1]; i += 1
            elif opt == "--limit" and i + 1 < len(opts):
                try:
                    rule["max_fires_per_hour"] = int(opts[i + 1]); i += 1
                except ValueError:
                    pass
            i += 1

        rules = cfg.get("automations", [])
        rules.append(rule)
        cfg.set("automations", rules)

        from telegcli.utils.automations import automation_engine
        automation_engine.restart()
        print_success(f"Rule added (#{len(rules)}): '{trigger}' → '{reply_text}'")

    elif sub == "remove":
        if len(args) < 2:
            print_error("Usage: automate remove <index>")
            return
        try:
            idx = int(args[1]) - 1
        except ValueError:
            print_error("Index must be an integer.")
            return
        rules = cfg.get("automations", [])
        if idx < 0 or idx >= len(rules):
            print_error(f"No rule at index {idx + 1}.")
            return
        removed = rules.pop(idx)
        cfg.set("automations", rules)
        from telegcli.utils.automations import automation_engine
        automation_engine.restart()
        print_success(f"Removed rule #{idx + 1}: '{removed.get('trigger')}'")

    elif sub in ("enable", "disable"):
        if len(args) < 2:
            print_error(f"Usage: automate {sub} <index>")
            return
        try:
            idx = int(args[1]) - 1
        except ValueError:
            print_error("Index must be an integer.")
            return
        rules = cfg.get("automations", [])
        if idx < 0 or idx >= len(rules):
            print_error(f"No rule at index {idx + 1}.")
            return
        rules[idx]["enabled"] = (sub == "enable")
        cfg.set("automations", rules)
        from telegcli.utils.automations import automation_engine
        automation_engine.restart()
        state = "enabled" if sub == "enable" else "disabled"
        print_success(f"Rule #{idx + 1} {state}.")

    elif sub == "clear":
        cfg.set("automations", [])
        from telegcli.utils.automations import automation_engine
        automation_engine.stop()
        print_success("All automations cleared.")
    else:
        print_error("Usage: automate [list|add|remove|enable|disable|clear]")


# ── template — Feature G ──────────────────────────────────────────────────────

async def cmd_template(args: list[str]) -> None:
    """
    template list
    template save <name> <text>
    template use  <name>  → prints the text (use with: send @chat --template <name>)
    template delete <name>
    """
    cfg = get_config()
    console = get_console()
    p = get_palette()
    sub = args[0].lower() if args else "list"

    if sub == "list":
        templates = cfg.get("templates", {})
        if not templates:
            print_info("No templates saved. Use: template save <name> <text>")
            return
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("Name",    style=p["accent"])
        table.add_column("Preview", style=p["fg"])
        for name, text in templates.items():
            preview = text[:60] + ("…" if len(text) > 60 else "")
            table.add_row(name, preview)
        console.print(table)

    elif sub == "save":
        if len(args) < 3:
            print_error("Usage: template save <name> <text>")
            return
        name = args[1]
        text = " ".join(args[2:])
        templates = cfg.get("templates", {})
        templates[name] = text
        cfg.set("templates", templates)
        print_success(f"Template '{name}' saved.")

    elif sub == "use":
        if len(args) < 2:
            print_error("Usage: template use <name>")
            return
        name = args[1]
        templates = cfg.get("templates", {})
        text = templates.get(name)
        if not text:
            print_error(f"Template '{name}' not found.")
            return
        console.print(Panel(
            text, title=f"[{p['accent']}]Template: {name}[/]",
            border_style=p["separator"],
        ))
        console.print(
            f"[{p['dim']}]Use with: send <chat> --template {name}[/]"
        )

    elif sub == "delete":
        if len(args) < 2:
            print_error("Usage: template delete <name>")
            return
        name = args[1]
        templates = cfg.get("templates", {})
        if name not in templates:
            print_error(f"Template '{name}' not found.")
            return
        del templates[name]
        cfg.set("templates", templates)
        print_success(f"Template '{name}' deleted.")
    else:
        print_error("Usage: template [list|save|use|delete]")


# ── draft — Feature B ─────────────────────────────────────────────────────────

async def cmd_draft(args: list[str]) -> None:
    """
    draft save <chat> <text>
    draft list
    draft send <id>
    draft delete <id>
    """
    cfg = get_config()
    console = get_console()
    p = get_palette()
    sub = args[0].lower() if args else "list"

    # Drafts stored as list of {id, chat, text, saved_at}
    drafts: list[dict] = cfg.get("drafts", [])

    if sub == "save":
        if len(args) < 3:
            print_error("Usage: draft save <chat> <text>")
            return
        chat_id = args[1]
        text = " ".join(args[2:])
        draft = {
            "id":       len(drafts) + 1,
            "chat":     chat_id,
            "text":     text,
            "saved_at": datetime.now().isoformat(),
        }
        drafts.append(draft)
        cfg.set("drafts", drafts)
        print_success(f"Draft #{draft['id']} saved for {chat_id}.")

    elif sub == "list":
        if not drafts:
            print_info("No drafts. Use: draft save <chat> <text>")
            return
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("#",     style=p["dim"], width=4)
        table.add_column("Chat",  style=p["accent"])
        table.add_column("Text",  style=p["fg"], ratio=3)
        table.add_column("Saved", style=p["timestamp"])
        for d in drafts:
            preview = d["text"][:50] + ("…" if len(d["text"]) > 50 else "")
            table.add_row(str(d["id"]), d["chat"], preview, d.get("saved_at", "")[:16])
        console.print(table)

    elif sub == "send":
        if len(args) < 2:
            print_error("Usage: draft send <id>")
            return
        try:
            did = int(args[1])
        except ValueError:
            print_error("ID must be an integer.")
            return
        draft = next((d for d in drafts if d["id"] == did), None)
        if not draft:
            print_error(f"Draft #{did} not found.")
            return
        entity = await resolve_entity(draft["chat"])
        if entity is None:
            return
        msg = await tg.send_message(entity, draft["text"])
        print_success(f"Draft #{did} sent → #{msg.id}")
        # Remove sent draft
        drafts = [d for d in drafts if d["id"] != did]
        cfg.set("drafts", drafts)

    elif sub == "delete":
        if len(args) < 2:
            print_error("Usage: draft delete <id>")
            return
        try:
            did = int(args[1])
        except ValueError:
            print_error("ID must be an integer.")
            return
        before = len(drafts)
        drafts = [d for d in drafts if d["id"] != did]
        cfg.set("drafts", drafts)
        if len(drafts) < before:
            print_success(f"Draft #{did} deleted.")
        else:
            print_error(f"Draft #{did} not found.")
    else:
        print_error("Usage: draft [save|list|send|delete]")


# ── sessions — Feature I / fix #9 ────────────────────────────────────────────

async def cmd_sessions(args: list[str]) -> None:
    """
    sessions list           → show all known sessions
    sessions switch <name>  → restart with named session (requires re-launch)
    sessions add <name>     → create a new named session (requires re-launch)
    """
    cfg = get_config()
    console = get_console()
    p = get_palette()
    sub = args[0].lower() if args else "list"

    import glob
    session_dir = cfg.config_dir
    session_files = list(session_dir.glob("*.session"))
    current = cfg.get("session_name", "telegcli")

    if sub == "list":
        if not session_files:
            print_info("No sessions found.")
            return
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("Name",    style=p["fg"])
        table.add_column("File",    style=p["dim"])
        table.add_column("Active",  width=8)
        for sf in session_files:
            name = sf.stem
            active = "✓ current" if name == current else ""
            table.add_row(name, str(sf), active)
        console.print(table)
        console.print(
            f"\n[{p['dim']}]Switch with: telegcli --session <name>[/]"
        )

    elif sub == "switch":
        if len(args) < 2:
            print_error("Usage: sessions switch <name>")
            return
        name = args[1]
        session_file = session_dir / f"{name}.session"
        if not session_file.exists():
            print_warning(f"Session '{name}' not found. It will be created on next launch.")
        console.print(
            Panel(
                f"[{p['fg']}]Restart telegcli with:[/]\n\n"
                f"  [{p['accent']}]telegcli --session {name}[/]",
                title=f"[{p['accent']}]Switch Session[/]",
                border_style=p["separator"],
            )
        )

    elif sub == "add":
        if len(args) < 2:
            print_error("Usage: sessions add <name>")
            return
        name = args[1]
        console.print(
            Panel(
                f"[{p['fg']}]Launch a new telegcli instance with:[/]\n\n"
                f"  [{p['accent']}]telegcli --session {name}[/]\n\n"
                f"[{p['dim']}]You will be prompted to authenticate the new account.[/]",
                title=f"[{p['accent']}]Add Session: {name}[/]",
                border_style=p["separator"],
            )
        )
    else:
        print_error("Usage: sessions [list|switch|add]")


# ── theme — fix #16 ───────────────────────────────────────────────────────────

VALID_THEMES = ("dark", "light", "gruvbox", "tokyo")


async def cmd_theme(args: list[str]) -> None:
    """theme <dark|light|gruvbox|tokyo>"""
    console = get_console()
    p = get_palette()
    cfg = get_config()

    if not args:
        current = cfg.get("theme", "dark")
        console.print(f"[{p['dim']}]Current:[/] [{p['accent']}]{current}[/]")
        console.print(f"[{p['dim']}]Available:[/]  " + "  ".join(VALID_THEMES))
        return

    theme = args[0].lower()
    if theme not in VALID_THEMES:
        print_error(f"Unknown theme '{theme}'. Choose: {', '.join(VALID_THEMES)}")
        return

    cfg.set("theme", theme)
    # Fix #16: refresh console so next output uses new colours
    refresh_console()
    # The REPL reads _prompt_style() per-prompt so it auto-updates too
    print_success(f"Theme set to '{theme}'. Prompt updates on next input.")


# ── config ────────────────────────────────────────────────────────────────────

async def cmd_config(args: list[str]) -> None:
    """config | config <key> | config <key> <val> | config reset"""
    console = get_console()
    p = get_palette()
    cfg = get_config()

    if not args:
        console.print(Panel(
            cfg.dump(),
            title=f"[{p['accent']}]Config[/]",
            border_style=p["separator"], padding=(1, 2),
        ))
        return

    if args[0] == "reset":
        cfg.reset()
        print_success("Config reset to defaults.")
        return

    key = args[0]
    if len(args) == 1:
        val = cfg.get(key, "<not set>")
        console.print(f"[{p['dim']}]{key}[/] = [{p['fg']}]{val}[/]")
        return

    raw = " ".join(args[1:])
    if raw.lower() == "true":
        val: object = True
    elif raw.lower() == "false":
        val = False
    elif raw.lstrip("-").isdigit():
        val = int(raw)
    else:
        val = raw

    cfg.set(key, val)
    print_success(f"{key} = {val}")


# ── logout ────────────────────────────────────────────────────────────────────

async def cmd_logout(args: list[str]) -> None:
    """
    logout [--yes] [--all-sessions]

    Logs out from Telegram and removes local credentials.
    - Clears api_id/api_hash from config.
    - Deletes current session file(s) from config dir.
    - With --all-sessions, deletes every *.session file.
    """
    cfg = get_config()

    force = "--yes" in args
    all_sessions = "--all-sessions" in args

    if not force:
        answer = (await _ask("Log out and delete local credentials? [y/N]")).strip().lower()
        if answer not in ("y", "yes"):
            print_info("Cancelled.")
            return

    # Revoke Telegram auth key if connected.
    try:
        if getattr(tg, "raw", None):
            await tg.raw.log_out()
    except Exception as e:
        log.warning("Remote logout failed: %s", e)
        print_warning("Could not revoke remote session cleanly. Continuing local cleanup.")

    try:
        await tg.disconnect()
    except Exception:
        pass

    deleted_files = 0
    pending_cleanup: list[str] = []

    if all_sessions:
        targets = [p for pat in ("*.session", "*.session-journal") for p in cfg.config_dir.glob(pat)]
    else:
        session_name = cfg.get("session_name", "telegcli")
        targets = [
            cfg.config_dir / f"{session_name}.session",
            cfg.config_dir / f"{session_name}.session-journal",
        ]

    for path in targets:
        if not path.exists():
            continue
        try:
            path.unlink(missing_ok=True)
            deleted_files += 1
        except OSError as e:
            pending_cleanup.append(str(path))
            log.warning("Deferred session cleanup for %s: %s", path, e)

    if pending_cleanup:
        cfg.set("pending_session_cleanup", pending_cleanup)
        print_warning(
            "Some session files are locked right now and will be deleted when the app exits."
        )
    else:
        cfg.set("pending_session_cleanup", [])

    cfg.set("api_id", 0)
    cfg.set("api_hash", "")

    scope = "all sessions" if all_sessions else "current session"
    print_success(
        f"Logged out. Removed {deleted_files} local session file(s) for {scope}, and cleared API credentials."
    )
    print_info("Run 'quit' now. On exit, any deferred cleanup will complete and next launch will ask for credentials.")


# ── clear / help ──────────────────────────────────────────────────────────────

async def cmd_clear(args: list[str]) -> None:
    os.system("clear" if os.name != "nt" else "cls")


async def cmd_help(args: list[str]) -> None:
    console = get_console()
    p = get_palette()

    if args:
        cmd = args[0].lower()
        desc = COMMANDS.get(cmd)
        if desc:
            console.print(f"[{p['accent']}]{cmd}[/]  [{p['dim']}]{desc}[/]")
        else:
            print_warning(f"Unknown command: {cmd}")
        return

    table = Table(
        box=box.SIMPLE, show_header=True,
        header_style=f"bold {p['accent']}", padding=(0, 2),
    )
    table.add_column("Command",     style=p["accent"], no_wrap=True)
    table.add_column("Description", style=p["fg"])

    groups = {
        "Messages":   ["read", "send", "reply", "edit", "delete", "forward",
                       "react", "pin", "unpin", "copy", "thread"],
        "Chats":      ["list", "info", "search", "gsearch", "mute", "unmute",
                       "archive", "markread"],
        "Files":      ["upload", "download", "gallery"],
        "Live":       ["watch"],
        "Contacts":   ["contacts", "add", "block", "unblock"],
        "Analysis":   ["stats", "export"],
        "Productivity": ["schedule", "template", "draft", "automate"],
        "Sessions":   ["sessions"],
        "Utility":    ["me", "theme", "config", "logout", "clear", "help", "quit"],
    }

    for group, cmds in groups.items():
        table.add_row(f"[bold {p['accent2']}]── {group} ──[/]", "")
        for cmd in cmds:
            desc = COMMANDS.get(cmd, "")
            table.add_row(f"  {cmd}", desc)

    console.print(Rule(f"[{p['accent']}]telegcli commands[/]", style=p["separator"]))
    console.print(table)
    console.print(
        f"\n  [{p['dim']}]Tab[/]  autocomplete  ·  "
        f"[{p['dim']}]↑↓[/]  history  ·  "
        f"[{p['dim']}]Ctrl+C[/]  interrupt  ·  "
        f"[{p['dim']}]Ctrl+L[/]  clear screen\n"
        f"  [{p['dim']}]read --json[/]  machine-readable output  ·  "
        f"[{p['dim']}]stats --json[/]  JSON stats\n"
    )
