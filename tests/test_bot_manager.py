"""Tests for token-based bot profile manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_bot_manager_profile_lifecycle(tmp_path):
    from telegcli.core.config import Config

    cfg = Config(config_dir=tmp_path)
    with patch("telegcli.bot.manager.get_config", return_value=cfg):
        from telegcli.bot.manager import BotManager

        mgr = BotManager()
        mgr.add_profile("demo", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcd")
        assert len(mgr.list_profiles()) == 1

        mgr.use_profile("demo")
        assert mgr.get_active_profile_name() == "demo"

        removed = mgr.remove_profile("demo")
        assert removed is True
        assert mgr.list_profiles() == []


@pytest.mark.asyncio
async def test_bot_manager_rejects_invalid_token(tmp_path):
    from telegcli.core.config import Config

    cfg = Config(config_dir=tmp_path)
    with patch("telegcli.bot.manager.get_config", return_value=cfg):
        from telegcli.bot.manager import BotManager

        mgr = BotManager()
        with pytest.raises(ValueError):
            mgr.add_profile("demo", "not-a-token")


@pytest.mark.asyncio
async def test_bot_manager_start_stop_uses_service(tmp_path):
    from telegcli.core.config import Config

    cfg = Config(config_dir=tmp_path)
    cfg.set("bot_profiles", [{"name": "demo", "token": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcd", "mode": "polling"}])
    cfg.set("bot_active_profile", "demo")

    fake_service = MagicMock()
    fake_service.profile_name = "demo"
    fake_service.running = False
    fake_service.start = AsyncMock()
    fake_service.stop = AsyncMock()

    with patch("telegcli.bot.manager.get_config", return_value=cfg), \
         patch("telegcli.bot.manager.BotService", return_value=fake_service):
        from telegcli.bot.manager import BotManager

        mgr = BotManager()
        svc = await mgr.start()
        assert svc is fake_service
        fake_service.start.assert_awaited_once()

        await mgr.stop()
        fake_service.stop.assert_awaited_once()
