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

# Command descriptions: short but clear with examples for complex commands
COMMANDS = {
    # Messages
    "send":      "✍️  Send a message  |  send 1 Hello!  |  send @chat Message here",
    "reply":     "💬 Reply to specific message  |  reply 1 42 Thanks!",
    "edit":      "✏️  Edit your message  |  edit 1 42 New text",
    "delete":    "🗑️  Delete message everywhere  |  delete 1 42  |  delete 1 10-20 --force",
    "forward":   "→ Forward message to another chat  |  forward 1 42 @saved  |  forward 1 42 @chat --edit",
    "react":     "😊 React with emoji  |  react 1 42 👍  |  react 1 42 ❤️",
    "copy":      "📋 Copy message text to clipboard  |  copy 1 42",
    "preview":   "🖼️  Show image as ASCII art  |  preview 1 42",
    "thread":    "🧵 Show message + all replies  |  thread 1 42",
    
    # Chats
    "list":      "📋 Show recent chats with latest message  |  list 30  |  list 25 --preview",
    "read":      "📖 Read messages from a chat  |  read 1  |  read @friend --first-unread  |  read 1 --type photo",
    "search":    "🔍 Search in dialog names  |  search john  |  search work group",
    "search":    "🔍 Search in dialog names  |  search john  |  search work group",
    "gsearch":   "🔎 Search across all messages  |  gsearch invoice 2024",
    "info":      "ℹ️  View chat or user details  |  info 1  |  info @username",
    "pins":      "📌 Show pinned messages in chat  |  pins 1  |  pins @friend 50",
    "mute":      "🔇 Mute notifications  |  mute 1",
    "unmute":    "🔔 Unmute notifications  |  unmute 1",
    "archive":   "📦 Archive chat (hide from main list)  |  archive 1",
    "markread":  "✓ Mark all messages as read  |  markread 1",
    "gallery":   "🎞️  List all photos & media  |  gallery 1  |  gallery 1 100",
    
    # Files
    "upload":    "📤 Send file/photo  |  upload 1 ~/photo.jpg  |  upload 1 file.pdf",
    "download":  "📥 Save media to computer  |  download 1 42",
    
    # Pin/Unpin
    "pin":       "📌 Pin message to chat  |  pin 1 42",
    "unpin":     "📍 Unpin message  |  unpin 1 42",
    
    # Contacts
    "contacts":  "👥 List all your saved contacts",
    "add":       "➕ Add contact  |  add +1234567890 John Smith",
    "block":     "🚫 Block user from messaging  |  block 1",
    "unblock":   "✅ Unblock user  |  unblock 1",
    
    # Watch
    "watch":     "📡 See new messages as they arrive  |  watch  |  watch @friend  |  Type 'r <text>' to quick reply",
    
    # Analytics
    "stats":     "📊 Chat statistics (daily/hourly breakdown)  |  stats 1  |  stats 1 500",
    "export":    "💾 Export chat as JSON/CSV/HTML  |  export 1 200 --format csv",
    
    # Auto-tasks
    "schedule":  "⏰ Send message at specific time  |  schedule 1 2025-12-31 09:00 Happy New Year!",
    "scheduled": "📅 List scheduled messages in chat  |  scheduled 1  |  scheduled @friend",
    "cancel-scheduled": "❌ Cancel a scheduled message  |  cancel-scheduled 1 5",
    "automate":  "🤖 Auto-reply rules  |  automate add  |  automate list",
    "template":  "🔖 Save & reuse messages  |  template save greet Hi!  |  template use greet",
    "draft":     "📝 Save draft messages  |  draft save @chat My message  |  draft send 1  |  Auto-saves every 30s",
    "snippet":   "🎯 Smart snippets & templates  |  snippet save hello Hi!  |  snippet use 1 hello",
    "reactions": "😊 See who reacted to message  |  reactions 1 42  |  reactions @chat 123 --json",
    "analytics": "📊 Advanced chat analytics  |  analytics 1 --daily  |  analytics @chat --top-senders",
    "tag":       "🏷️  Organize chats with tags  |  tag add 1 work  |  tag list  |  tag show work",
    "group":     "📂 Create named groups of tagged chats  |  group create work @work  |  group list",
    "backup":    "💾 Full backup/export with compression  |  backup ~/backup.tar.gz  |  backup ~/msgs.json --format json",
    "restore":   "📥 Restore messages from backup  |  restore ~/backup.tar.gz --preview  |  restore ~/backup.tar.gz --chat 1",
    "workflow":  "⚙️  Advanced automations with conditions  |  workflow create myrule  |  workflow list  |  workflow run myrule",
    
    # Sessions
    "sessions":  "🔐 Switch between accounts  |  sessions list  |  sessions switch work",
    
    # Bot mode
    "bot":       "🤖 Bot service (Telegram Bot API)  |  bot create  |  bot start  |  bot doctor  |  help bot",
    
    # Utility
    "me":        "👤 Your account info (phone, name, username)",
    "theme":     "🎨 Change color scheme  |  theme dark  |  theme gruvbox",
    "shortcuts": "⌨️  Display keyboard shortcuts and tips",
    "config":    "⚙️  View/change settings  |  config  |  config msg_limit 100",
    "logout":    "🚪 Log out and clear session",
    "clear":     "🔲 Clear screen",
    "help":      "❓ Show help  |  help  |  help read",
    "quit":      "👋 Exit telegcli",
    "exit":      "👋 Exit telegcli",
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
