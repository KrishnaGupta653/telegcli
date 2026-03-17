"""
telegcli.utils.automations
────────────────────────
Production-grade automation engine.

Fixes applied:
  #5  — Double-handler guard: start() is idempotent
  #6  — Uses registry='automation' so watch cleanup doesn't kill automations
  #10 — Rules support chat_filter, user_filter, only_private, max_fires_per_hour
        Fires are skipped for outgoing messages (msg.out check)
        automate remove <index> is now supported

Rule schema (all fields except trigger+reply are optional):
  {
    "trigger":           "keyword",      # substring match (case-insensitive)
    "reply":             "response text",
    "chat_filter":       "@username",    # only fire in this chat (None = all)
    "user_filter":       "@username",    # only fire when this user sends
    "only_private":      true,           # only DMs, skip groups/channels
    "max_fires_per_hour": 5,             # rate-cap per rule
    "enabled":           true
  }
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

from telegcli.core.client import tg
from telegcli.core.config import get_config
from telegcli.ui.theme import get_console, get_palette

log = logging.getLogger("telegcli.automations")


class AutomationEngine:
    """Runs in the background and processes incoming messages against rules."""

    def __init__(self) -> None:
        self._running: bool = False
        # fire-count buckets: rule_index → list[timestamp]
        self._fire_times: dict[int, list[float]] = defaultdict(list)

    # ── lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Idempotent: safe to call multiple times. Fix #5."""
        cfg = get_config()
        rules = cfg.get("automations", [])

        if self._running:
            log.debug("AutomationEngine.start() called while already running — skipped")
            return

        if not rules:
            return

        self._running = True
        # Use separate 'automation' registry so watch doesn't remove us (fix #6)
        tg.on_new_message(self._handler, incoming=True, registry="automation")

        console = get_console()
        p = get_palette()
        console.print(
            f"[{p['dim']}]  Automation engine started "
            f"({len(rules)} rule(s))[/]"
        )
        log.info("AutomationEngine started with %d rules", len(rules))

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        tg.remove_automation_handlers()
        self._fire_times.clear()
        log.info("AutomationEngine stopped")

    def restart(self) -> None:
        """Called after rules are modified."""
        self.stop()
        self.start()

    # ── handler ───────────────────────────────────────────────────────

    async def _handler(self, event) -> None:
        if not self._running:
            return

        msg = event.message

        # Skip outgoing messages (fix #10)
        if msg.out:
            return

        text = (msg.text or "").lower()
        if not text:
            return

        cfg = get_config()
        rules: list[dict] = cfg.get("automations", [])

        for idx, rule in enumerate(rules):
            if not rule.get("enabled", True):
                continue

            trigger = rule.get("trigger", "").lower()
            reply_text = rule.get("reply", "")
            if not trigger or not reply_text:
                continue

            if trigger not in text:
                continue

            # only_private filter (fix #10)
            if rule.get("only_private", False):
                try:
                    chat = await event.get_chat()
                    from telethon.tl.types import User
                    if not isinstance(chat, User):
                        continue
                except Exception:
                    continue

            # chat_filter (fix #10)
            chat_filter = rule.get("chat_filter", "").strip()
            if chat_filter:
                try:
                    chat = await event.get_chat()
                    name = getattr(chat, "username", "") or ""
                    title = getattr(chat, "title", "") or getattr(chat, "first_name", "") or ""
                    if chat_filter.lstrip("@").lower() not in (
                        name.lower(), title.lower()
                    ):
                        continue
                except Exception:
                    continue

            # user_filter (fix #10)
            user_filter = rule.get("user_filter", "").strip()
            if user_filter and event.sender:
                sender_name = getattr(event.sender, "username", "") or ""
                if user_filter.lstrip("@").lower() != sender_name.lower():
                    continue

            # max_fires_per_hour rate cap (fix #10)
            max_fph = rule.get("max_fires_per_hour", 0)
            if max_fph > 0:
                now = time.monotonic()
                bucket = self._fire_times[idx]
                # Expire entries older than 1 hour
                self._fire_times[idx] = [t for t in bucket if now - t < 3600]
                if len(self._fire_times[idx]) >= max_fph:
                    log.debug("Rule %d: max_fires_per_hour %d reached", idx, max_fph)
                    continue
                self._fire_times[idx].append(now)

            # Fire
            try:
                await asyncio.sleep(0.8)   # natural delay
                await tg.send_message(
                    await event.get_chat(),
                    reply_text,
                    reply_to=msg.id,
                )
                log.info(
                    "Automation rule %d fired: trigger=%r chat=%s",
                    idx, trigger, event.chat_id,
                )
            except Exception as exc:
                log.warning("Auto-reply failed (rule %d): %s", idx, exc)


automation_engine = AutomationEngine()
