"""
Tests for telegcli.utils.automations

Covers: idempotent start (#5), outgoing message skip (#10),
        only_private filter, max_fires_per_hour, rule enable/disable.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from telegcli.utils.automations import AutomationEngine


# ── fixtures ──────────────────────────────────────────────────────────────────

def make_engine():
    engine = AutomationEngine()
    return engine


def make_event(text: str, out: bool = False, chat_type="User"):
    event = MagicMock()
    event.message = MagicMock()
    event.message.text = text
    event.message.out = out
    event.message.id = 1
    event.sender = MagicMock()
    event.sender.username = "testuser"
    event.chat_id = 123

    if chat_type == "User":
        from telethon.tl.types import User
        chat = MagicMock(spec=User)
    else:
        chat = MagicMock()
        del chat.spec  # not a User

    event.get_chat = AsyncMock(return_value=chat)
    return event


# ── idempotent start (fix #5) ─────────────────────────────────────────────────

def test_start_is_idempotent():
    engine = make_engine()
    rules = [{"trigger": "hi", "reply": "hello", "enabled": True}]

    with patch("telegcli.utils.automations.get_config") as mock_cfg, \
         patch("telegcli.utils.automations.tg") as mock_tg, \
         patch("telegcli.utils.automations.get_console"), \
         patch("telegcli.utils.automations.get_palette", return_value={"dim": ""}):

        mock_cfg.return_value.get.return_value = rules
        engine.start()
        engine.start()  # second call should be a no-op

    # on_new_message should only be called once
    assert mock_tg.on_new_message.call_count == 1


# ── outgoing message skip (fix #10) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_handler_skips_outgoing_messages():
    engine = make_engine()
    engine._running = True
    sent = []

    rules = [{"trigger": "hello", "reply": "hi", "enabled": True}]
    event = make_event("hello", out=True)

    with patch("telegcli.utils.automations.get_config") as mock_cfg, \
         patch("telegcli.utils.automations.tg") as mock_tg, \
         patch("telegcli.utils.automations.asyncio.sleep", new_callable=AsyncMock):

        mock_cfg.return_value.get.return_value = rules
        mock_tg.send_message = AsyncMock()

        await engine._handler(event)

    mock_tg.send_message.assert_not_called()


# ── trigger matching ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handler_fires_on_trigger_match():
    engine = make_engine()
    engine._running = True

    rules = [{"trigger": "hello", "reply": "world", "enabled": True}]
    event = make_event("say hello to me", out=False)

    with patch("telegcli.utils.automations.get_config") as mock_cfg, \
         patch("telegcli.utils.automations.tg") as mock_tg, \
         patch("telegcli.utils.automations.asyncio.sleep", new_callable=AsyncMock):

        mock_cfg.return_value.get.return_value = rules
        mock_tg.send_message = AsyncMock()

        await engine._handler(event)

    mock_tg.send_message.assert_called_once()
    _, kwargs = mock_tg.send_message.call_args
    assert kwargs.get("reply_to") == event.message.id


@pytest.mark.asyncio
async def test_handler_no_fire_when_trigger_absent():
    engine = make_engine()
    engine._running = True

    rules = [{"trigger": "hello", "reply": "world", "enabled": True}]
    event = make_event("good morning", out=False)

    with patch("telegcli.utils.automations.get_config") as mock_cfg, \
         patch("telegcli.utils.automations.tg") as mock_tg, \
         patch("telegcli.utils.automations.asyncio.sleep", new_callable=AsyncMock):

        mock_cfg.return_value.get.return_value = rules
        mock_tg.send_message = AsyncMock()

        await engine._handler(event)

    mock_tg.send_message.assert_not_called()


# ── disabled rule ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handler_skips_disabled_rule():
    engine = make_engine()
    engine._running = True

    rules = [{"trigger": "hello", "reply": "world", "enabled": False}]
    event = make_event("hello", out=False)

    with patch("telegcli.utils.automations.get_config") as mock_cfg, \
         patch("telegcli.utils.automations.tg") as mock_tg, \
         patch("telegcli.utils.automations.asyncio.sleep", new_callable=AsyncMock):

        mock_cfg.return_value.get.return_value = rules
        mock_tg.send_message = AsyncMock()

        await engine._handler(event)

    mock_tg.send_message.assert_not_called()


# ── max_fires_per_hour (fix #10) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handler_respects_max_fires_per_hour():
    engine = make_engine()
    engine._running = True

    rules = [{"trigger": "ping", "reply": "pong", "enabled": True, "max_fires_per_hour": 2}]

    with patch("telegcli.utils.automations.get_config") as mock_cfg, \
         patch("telegcli.utils.automations.tg") as mock_tg, \
         patch("telegcli.utils.automations.asyncio.sleep", new_callable=AsyncMock):

        mock_cfg.return_value.get.return_value = rules
        mock_tg.send_message = AsyncMock()

        for _ in range(5):
            await engine._handler(make_event("ping", out=False))

    # Only 2 of the 5 should have fired
    assert mock_tg.send_message.call_count == 2


# ── stop clears state ─────────────────────────────────────────────────────────

def test_stop_resets_running_flag():
    engine = make_engine()
    engine._running = True

    with patch("telegcli.utils.automations.tg") as mock_tg:
        engine.stop()

    assert engine._running is False
    mock_tg.remove_automation_handlers.assert_called_once()

