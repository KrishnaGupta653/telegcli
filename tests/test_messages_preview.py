"""Tests for preview command behavior in messages commands."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_cmd_preview_usage_when_missing_args():
    with patch("telegcli.commands.messages.print_error") as print_error:
        from telegcli.commands.messages import cmd_preview
        await cmd_preview([])
        print_error.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_preview_rejects_non_integer_message_id():
    with patch("telegcli.commands.messages.resolve_entity", new=AsyncMock(return_value=MagicMock())), \
         patch("telegcli.commands.messages.print_error") as print_error:
        from telegcli.commands.messages import cmd_preview
        await cmd_preview(["1", "abc"])
        print_error.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_preview_warns_when_non_image_message():
    fake_msg = MagicMock()

    fake_tg = MagicMock()
    fake_tg.raw = MagicMock()
    fake_tg.raw.get_messages = AsyncMock(return_value=fake_msg)

    fake_console = MagicMock()
    fake_status_cm = MagicMock()
    fake_status_cm.__enter__ = MagicMock(return_value=None)
    fake_status_cm.__exit__ = MagicMock(return_value=None)
    fake_console.status = MagicMock(return_value=fake_status_cm)

    with patch("telegcli.commands.messages.resolve_entity", new=AsyncMock(return_value=MagicMock())), \
         patch("telegcli.commands.messages.tg", fake_tg), \
         patch("telegcli.commands.messages.get_console", return_value=fake_console), \
         patch("telegcli.commands.messages.get_config") as get_config, \
         patch("telegcli.commands.messages.is_image_message", return_value=False), \
         patch("telegcli.commands.messages.print_warning") as print_warning:
        get_config.return_value = MagicMock(get=MagicMock(return_value=56))
        from telegcli.commands.messages import cmd_preview
        await cmd_preview(["1", "42"])
        print_warning.assert_called_once()
