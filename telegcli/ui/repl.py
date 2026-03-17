"""
telegcli.ui.repl
─────────────
Production-grade async REPL.

Fixes applied:
  #8  — All blocking I/O (Prompt.ask, input, getpass) replaced with
         prompt_toolkit's prompt_async() throughout the app layer.
         The REPL itself is fully async.
  #16 — Theme-aware prompt: _prompt_style() is called per-prompt,
         not once at session build time.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Awaitable, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style as PtkStyle
from prompt_toolkit.key_binding import KeyBindings

from telegcli.core.config import get_config

COMMANDS = {
    "list":      "List recent chats",
    "read":      "Read messages  — read <n> [count]",
    "send":      "Send a message — send <n> [text]",
    "reply":     "Reply to a msg — reply <n> <msg_id> [text]",
    "edit":      "Edit a message — edit <n> <msg_id> [text]",
    "delete":    "Delete messages — delete <n> <msg_id> [--local]",
    "forward":   "Forward a msg  — forward <from> <msg_id> <to>",
    "react":     "React to a msg — react <n> <msg_id> [emoji]",
    "search":    "Search dialogs — search <query>",
    "gsearch":   "Global search  — gsearch <query>",
    "info":      "Chat/user info  — info <n>",
    "upload":    "Upload a file  — upload <n> <path> [caption]",
    "download":  "Download media — download <n> <msg_id> [dest]",
    "gallery":   "Media gallery  — gallery <n> [count]",
    "watch":     "Live message stream — watch [chat]",
    "contacts":  "List contacts",
    "add":       "Add a contact  — add <phone> <name>",
    "block":     "Block a user   — block <n>",
    "unblock":   "Unblock a user — unblock <n>",
    "mute":      "Mute a chat    — mute <n>",
    "unmute":    "Unmute a chat  — unmute <n>",
    "archive":   "Archive a chat — archive <n>",
    "markread":  "Mark as read   — markread <n>",
    "pin":       "Pin a message  — pin <n> <msg_id>",
    "unpin":     "Unpin a message — unpin <n> <msg_id>",
    "copy":      "Copy message to clipboard — copy <n> <msg_id>",
    "me":        "Your account info",
    "schedule":  "Schedule a message — schedule <n> <YYYY-MM-DD HH:MM> <text>",
    "automate":  "Manage automations — automate [list|add|remove|clear]",
    "template":  "Message templates — template [save|use|list|delete]",
    "draft":     "Saved drafts — draft [save|list|send|delete]",
    "export":    "Export chat — export <n> [count] [--format json|csv|txt|html]",
    "stats":     "Chat statistics — stats <n> [count]",
    "thread":    "Show message thread — thread <n> <msg_id>",
    "sessions":  "Manage accounts — sessions [list|switch|add]",
    "theme":     "Switch theme — theme <dark|light|gruvbox|tokyo>",
    "config":    "Show/set config — config [key] [value]",
    "logout":    "Log out and delete local credentials/session",
    "clear":     "Clear the screen",
    "help":      "Show help",
    "quit":      "Exit telecli",
    "exit":      "Exit telecli",
}


class TgCompleter(Completer):
    """Context-aware completer: first word → command, second+ → dialog names."""

    def __init__(self, dialog_names: list[str]) -> None:
        self._dialog_names = dialog_names

    def update_dialogs(self, names: list[str]) -> None:
        self._dialog_names = names

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words = text.split()

        if len(words) == 0 or (len(words) == 1 and not text.endswith(" ")):
            word = words[0] if words else ""
            for cmd, desc in COMMANDS.items():
                if cmd.startswith(word):
                    yield Completion(
                        cmd,
                        start_position=-len(word),
                        display=cmd,
                        display_meta=desc,
                    )
            return

        if len(words) >= 2:
            partial = words[-1] if not text.endswith(" ") else ""
            for name in self._dialog_names:
                if partial.lower() in name.lower():
                    safe = f'"{name}"' if " " in name else name
                    yield Completion(
                        safe,
                        start_position=-len(partial),
                        display=name,
                    )


def _prompt_style() -> PtkStyle:
    """Build prompt style from current theme — called per-prompt for live updates. Fix #16."""
    cfg = get_config()
    theme = cfg.get("theme", "dark")
    if theme == "dark":
        return PtkStyle.from_dict({
            "prompt":   "#7aa2f7 bold",
            "rprompt":  "#565f89",
            "completion-menu.completion":         "bg:#24283b #c0caf5",
            "completion-menu.completion.current": "bg:#2d3f76 #7aa2f7 bold",
            "completion-menu.meta.completion":    "#565f89",
        })
    elif theme == "gruvbox":
        return PtkStyle.from_dict({
            "prompt":   "#83a598 bold",
            "rprompt":  "#928374",
            "completion-menu.completion":         "bg:#32302f #ebdbb2",
            "completion-menu.completion.current": "bg:#504945 #83a598 bold",
        })
    elif theme == "tokyo":
        return PtkStyle.from_dict({
            "prompt":   "#7dcfff bold",
            "rprompt":  "#444b6a",
            "completion-menu.completion":         "bg:#1f2335 #a9b1d6",
            "completion-menu.completion.current": "bg:#2d3f76 #7dcfff bold",
        })
    else:  # light
        return PtkStyle.from_dict({
            "prompt":   "#4078f2 bold",
            "rprompt":  "#9ca0a4",
        })


def _make_keybindings() -> KeyBindings:
    kb = KeyBindings()

    @kb.add("c-l")
    def clear_screen(event):
        event.app.renderer.clear()

    return kb


class Repl:
    """Fully async REPL loop."""

    def __init__(self) -> None:
        self._dialog_names: list[str] = []
        self._completer = TgCompleter(self._dialog_names)
        self._session: Optional[PromptSession] = None
        self._me_name: str = "you"
        self._current_chat: str = ""

    def set_me(self, name: str) -> None:
        self._me_name = name

    def set_current_chat(self, name: str) -> None:
        self._current_chat = name

    def update_dialog_names(self, names: list[str]) -> None:
        self._completer.update_dialogs(names)
        self._dialog_names = names

    def _build_session(self) -> PromptSession:
        cfg = get_config()
        return PromptSession(
            history=FileHistory(str(cfg.config_dir / "history")),
            auto_suggest=AutoSuggestFromHistory(),
            completer=self._completer,
            complete_while_typing=True,
            # Style is NOT baked in here — passed dynamically per-prompt (fix #16)
            key_bindings=_make_keybindings(),
            mouse_support=False,
            enable_history_search=True,
        )

    def _prompt_text(self) -> HTML:
        chat_part = (
            f" <ansi_cyan>({self._current_chat})</ansi_cyan>"
            if self._current_chat else ""
        )
        return HTML(f"<ansi_blue><b>tg</b></ansi_blue>{chat_part} <ansi_blue>❯</ansi_blue> ")

    async def prompt_async(self, message: str = "") -> str:
        """Helper for commands that need to prompt the user asynchronously. Fix #8."""
        if self._session is None:
            self._session = self._build_session()
        return await self._session.prompt_async(
            HTML(f"<ansi_blue>{message}</ansi_blue> ") if message else "",
            style=_prompt_style(),
        )

    async def run(
        self,
        handler: Callable[[str, list[str]], Awaitable[None]],
    ) -> None:
        self._session = self._build_session()

        while True:
            try:
                # Pass style per-prompt so theme changes take effect live (fix #16)
                raw = await self._session.prompt_async(
                    self._prompt_text(),
                    rprompt=HTML(f"<ansi_white>{self._me_name}</ansi_white>"),
                    style=_prompt_style(),
                )
            except KeyboardInterrupt:
                continue
            except EOFError:
                print()
                break

            line = raw.strip()
            if not line:
                continue

            parts = _smart_split(line)
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("exit", "quit", "q"):
                break

            try:
                await handler(cmd, args)
            except Exception as e:
                from telegcli.ui.theme import print_error
                import logging
                logging.getLogger("telegcli.repl").exception("Unhandled error in command %r", cmd)
                print_error(f"Error: {e}")


def _smart_split(line: str) -> list[str]:
    import shlex
    try:
        return shlex.split(line)
    except ValueError:
        return line.split()
