"""
telegcli.app
─────────
Application orchestrator.

Fixes applied:
  #4  — secure session + config file permissions enforced at connect()
  #8  — all UI prompts are async via prompt_toolkit (repl.prompt_async)
  #9  — accepts Config instance injected by main.py (multi-session)
  #20 — Config and teleclient are injected, not imported as globals
"""

from __future__ import annotations

import asyncio
import getpass
import io
import logging
import re
import sys
from datetime import datetime
from typing import Optional

from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt

from telegcli.core.config import Config, get_config
from telegcli.core.client import teleclient, get_client
from telegcli.ui.theme import (
    get_console, print_banner, print_success, print_error,
    print_warning, print_info, get_palette, entity_name,
)
from telegcli.ui.repl import Repl
from telegcli.commands import DISPATCH
from telegcli.utils.automations import automation_engine

log = logging.getLogger("telegcli.app")


class TeleCli:
    def __init__(self, cfg: Optional[Config] = None) -> None:
        self._cfg = cfg or get_config()
        self._tg  = get_client()
        self._repl = Repl()
        self._autosave_task: Optional[asyncio.Task] = None

    # ── public entry point ────────────────────────────────────────────

    async def run(self) -> None:
        console = get_console()
        p = get_palette()

        if not self._cfg.get("no_color"):
            print_banner()

        # Step 1: credentials
        if not self._cfg.is_configured:
            await self._first_run_setup()
            if not self._cfg.is_configured:
                print_error("API credentials required. Exiting.")
                return

        if not self._credentials_look_valid():
            print_warning("Saved Telegram API credentials look invalid. Please re-enter them.")
            await self._first_run_setup()
            if not self._credentials_look_valid():
                print_error("Valid api_id/api_hash required. Exiting.")
                return

        # Step 2: connect
        console.print(f"[{p['dim']}]Connecting…[/]", end=" ")
        try:
            await self._tg.connect()
        except Exception as e:
            print_error(f"Connection failed: {e}")
            log.exception("Connection failed")
            return
        console.print(f"[{p['success']}]OK[/]")

        # Step 3: authenticate
        try:
            ok = await self._tg.ensure_authorized({
                "choose_login_method": self._choose_login_method,
                "get_phone":  self._prompt_phone,
                "get_code":   self._prompt_code,
                "get_2fa":    self._prompt_2fa,
                "show_qr":    self._show_qr,
                "show_error": self._show_error,
            })
        except Exception as e:
            print_error(f"Authentication failed: {e}")
            log.exception("Authentication failed")
            await self._tg.disconnect()
            return

        if not ok:
            print_error("Could not authenticate.")
            await self._tg.disconnect()
            return

        me = self._tg.me
        print_success(
            f"Logged in as [bold]{me.first_name}[/]"
            f"{f' (@{me.username})' if me.username else ''}"
        )
        log.info("Logged in as %s (%d)", me.first_name, me.id)

        # Step 4: warm up dialog cache + autocomplete
        console.print(f"[{p['dim']}]Loading chats…[/]", end=" ")
        try:
            from telegcli.utils.resolver import dialog_cache
            dialogs = await self._tg.get_dialogs(limit=50)
            dialog_cache.update(dialogs)
            names = [d.name or "" for d in dialogs if d.name]
            self._repl.update_dialog_names(names)
            console.print(f"[{p['dim']}]{len(dialogs)} loaded[/]")
        except Exception as e:
            console.print(f"[{p['warning']}]Warning: {e}[/]")
            log.warning("Dialog preload failed: %s", e)

        # Step 5: inject repl into commands that need async prompts (fix #8)
        from telegcli.commands import messages as _msg_mod
        from telegcli.commands import misc as _misc_mod
        _msg_mod.set_repl(self._repl)
        _misc_mod.set_repl(self._repl)

        # Step 6: start automation engine
        automation_engine.start()

        # Step 7: start auto-save drafts background task (Feature 14)
        self._autosave_task = asyncio.create_task(self._auto_save_drafts())

        # Step 8: set REPL context
        me_name = f"@{me.username}" if me.username else (me.first_name or "me")
        session_name = self._cfg.get("session_name", "telegcli")
        if session_name != "telegcli":
            me_name = f"{me_name} [{session_name}]"
        self._repl.set_me(me_name)

        console.print(
            f"\n[{p['dim']}]Type [/][{p['accent']}]help[/][{p['dim']}] or "
            f"[/][{p['accent']}]?[/][{p['dim']}] to see all commands. "
            f"Tab completes. ↑↓ for history.[/]\n"
        )

        # Step 9: REPL loop
        try:
            await self._repl.run(self._dispatch)
        finally:
            # Cancel auto-save task
            if self._autosave_task and not self._autosave_task.done():
                self._autosave_task.cancel()
                try:
                    await self._autosave_task
                except asyncio.CancelledError:
                    pass
            
            automation_engine.stop()
            try:
                from telegcli.bot.manager import get_bot_manager
                await get_bot_manager().stop()
            except Exception:
                pass
            await self._tg.disconnect()
            self._run_pending_session_cleanup()
            console.print(f"[{p['dim']}]Disconnected. Goodbye.[/]")
            log.info("Session ended cleanly")

    def _run_pending_session_cleanup(self) -> None:
        """Delete session files that were locked during in-session logout on Windows."""
        pending = self._cfg.get("pending_session_cleanup", [])
        if not pending:
            return

        removed = 0
        failed: list[str] = []
        for raw in pending:
            from pathlib import Path
            path = Path(raw)
            try:
                if path.exists():
                    path.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                failed.append(str(path))

        self._cfg.set("pending_session_cleanup", failed)
        if failed:
            log.warning("Pending session cleanup incomplete: %s", failed)
        elif removed:
            log.info("Deferred session cleanup completed (%d files)", removed)

    # ── auto-save drafts background task ──────────────────────────────

    async def _auto_save_drafts(self) -> None:
        """
        Feature 14: Auto-save REPL input buffer as draft every 30 seconds.
        Allows recovery of unsent messages in case of crash or disconnect.
        """
        try:
            while True:
                await asyncio.sleep(30)  # Save every 30 seconds
                
                try:
                    # Get current REPL input buffer
                    current_input = self._repl.session.app.current_buffer.text.strip()
                    
                    if current_input:
                        # Store as auto-draft
                        auto_drafts = self._cfg.get("auto_drafts", [])
                        
                        # Replace previous auto-draft with latest
                        auto_drafts = [
                            d for d in auto_drafts
                            if d.get("type") != "auto"
                        ]
                        
                        auto_drafts.append({
                            "type": "auto",
                            "text": current_input,
                            "saved_at": datetime.now().isoformat(),
                        })
                        
                        self._cfg.set("auto_drafts", auto_drafts)
                        log.debug("Auto-saved draft (%d chars)", len(current_input))
                except Exception:
                    # Don't crash if auto-save fails
                    log.debug("Auto-save draft failed", exc_info=True)
        except asyncio.CancelledError:
            # Task was cancelled (app shutting down)
            pass

    # ── command dispatcher ────────────────────────────────────────────

    async def _dispatch(self, cmd: str, args: list[str]) -> None:
        handler = DISPATCH.get(cmd)
        if handler is None:
            if cmd.isdigit():
                from telegcli.commands.messages import cmd_read
                await cmd_read([cmd] + args)
                return
            if cmd.startswith("@") or cmd.startswith("+"):
                from telegcli.commands.messages import cmd_read
                await cmd_read([cmd] + args)
                return
            print_warning(
                f"Unknown command: '{cmd}'.  "
                f"Type [bold]help[/] to list commands."
            )
            return

        try:
            await handler(args)
        except KeyboardInterrupt:
            print_warning("Interrupted.")
        except Exception as e:
            log.exception("Error in command %r", cmd)
            print_error(f"{type(e).__name__}: {e}")

    # ── first-run setup ───────────────────────────────────────────────

    async def _first_run_setup(self) -> None:
        console = get_console()
        p = get_palette()

        console.print(Panel(
            f"[{p['fg']}]To use telegcli you need Telegram API credentials.\n\n"
            f"1. Visit [link=https://my.telegram.org]{p['accent']}https://my.telegram.org[/]\n"
            f"2. Log in → [bold]API development tools[/]\n"
            f"3. Create an app (any name, platform: Desktop)\n"
            f"4. Copy your [bold]api_id[/] and [bold]api_hash[/][/]",
            title=f"[{p['accent']}]First-time Setup[/]",
            border_style=p["separator"],
        ))

        # Use run_in_executor so we don't block the event loop (fix #8)
        loop = asyncio.get_event_loop()
        try:
            raw_id = await loop.run_in_executor(
                None, lambda: Prompt.ask(f"[{p['accent']}]api_id[/]").strip()
            )
            api_id = int(raw_id)
        except (ValueError, KeyboardInterrupt):
            print_error("Invalid api_id.")
            return

        try:
            api_hash = await loop.run_in_executor(
                None, lambda: Prompt.ask(f"[{p['accent']}]api_hash[/]").strip()
            )
        except KeyboardInterrupt:
            return

        api_hash = api_hash.strip()
        if not api_hash:
            print_error("api_hash cannot be empty.")
            return

        if not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
            print_error(
                "Invalid api_hash format. It should be a 32-character hexadecimal string "
                f"(got length {len(api_hash)})."
            )
            return

        self._cfg.set("api_id", api_id)
        self._cfg.set("api_hash", api_hash)
        print_success("Credentials saved.")

    # ── auth prompts — all async via run_in_executor (fix #8) ─────────

    async def _prompt_phone(self) -> str:
        p = get_palette()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: Prompt.ask(
                f"[{p['accent']}]Phone number[/] (with country code, e.g. +91...)"
            )
        )

    async def _prompt_code(self) -> str:
        p = get_palette()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: Prompt.ask(f"[{p['accent']}]Telegram OTP[/]")
        )

    async def _choose_login_method(self) -> str:
        print_info("Login method: type 'phone' or 'qr' (default: phone)")

        for _ in range(3):
            raw = (await self._repl.prompt_async("login method [phone/qr]:")).strip().lower()
            if not raw:
                return "phone"
            if raw in {"phone", "qr"}:
                return raw
            print_warning("Please enter 'phone' or 'qr'.")

        print_warning("Too many invalid attempts. Using phone login.")
        return "phone"

    async def _show_qr(self, url: str) -> None:
        p = get_palette()
        console = get_console()

        try:
            import qrcode

            qr = qrcode.QRCode(border=1)
            qr.add_data(url)
            qr.make(fit=True)

            out = io.StringIO()
            qr.print_ascii(out=out, invert=True)
            ascii_qr = out.getvalue()

            console.print(Panel(
                (
                    f"[{p['fg']}]Open Telegram on your phone and scan this QR:\n\n[/]"
                    f"[{p['dim']}]Settings -> Devices -> Link Desktop Device[/]\n\n"
                    f"[{p['accent']}]Login URL:[/] {escape(url)}\n\n"
                    f"[{p['fg']}]{escape(ascii_qr)}[/]"
                ),
                title=f"[{p['accent']}]QR Login[/]",
                border_style=p["separator"],
            ))
        except ImportError:
            print_warning("QR rendering requires the 'qrcode' package, which is not installed.")
            print_info("Install it with: pip install qrcode")
            print_warning("Using login URL instead:")
            print_info(url)
        except Exception:
            print_warning("Could not render QR in terminal. Use this login URL instead:")
            print_info(url)

    async def _prompt_2fa(self) -> str:
        hint = await self._tg.get_password_hint()
        prompt_str = f"2FA password{f' (hint: {hint})' if hint else ''}: "
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, getpass.getpass, prompt_str)

    async def _show_error(self, msg: str) -> None:
        print_error(msg)

    def _credentials_look_valid(self) -> bool:
        api_id = self._cfg.get("api_id", 0)
        api_hash = str(self._cfg.get("api_hash", "")).strip()
        return isinstance(api_id, int) and api_id > 0 and bool(re.fullmatch(r"[0-9a-fA-F]{32}", api_hash))
