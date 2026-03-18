"""Bot profile + runtime manager for token-based bot mode."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from telegcli.core.config import get_config
from telegcli.bot.service import BotService

_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{10,}$")


@dataclass
class BotProfile:
    name: str
    token: str
    mode: str = "polling"


class BotManager:
    def __init__(self) -> None:
        self._service: Optional[BotService] = None

    def list_profiles(self) -> list[BotProfile]:
        cfg = get_config()
        profiles = cfg.get("bot_profiles", [])
        out: list[BotProfile] = []
        for p in profiles:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name", "")).strip()
            token = str(p.get("token", "")).strip()
            mode = str(p.get("mode", "polling")).strip() or "polling"
            if not name or not token:
                continue
            out.append(BotProfile(name=name, token=token, mode=mode))
        return out

    def get_active_profile_name(self) -> str:
        return str(get_config().get("bot_active_profile", "")).strip()

    def get_profile(self, name: Optional[str] = None) -> Optional[BotProfile]:
        target = name or self.get_active_profile_name()
        if not target:
            return None
        for p in self.list_profiles():
            if p.name == target:
                return p
        return None

    def add_profile(self, name: str, token: str, mode: str = "polling") -> None:
        name = name.strip()
        token = token.strip()
        if not name:
            raise ValueError("Profile name cannot be empty")
        if not _TOKEN_RE.match(token):
            raise ValueError("Invalid bot token format")

        cfg = get_config()
        profiles = [p for p in cfg.get("bot_profiles", []) if isinstance(p, dict)]

        replaced = False
        for p in profiles:
            if p.get("name") == name:
                p["token"] = token
                p["mode"] = mode
                replaced = True
                break
        if not replaced:
            profiles.append({"name": name, "token": token, "mode": mode})

        cfg.set("bot_profiles", profiles)
        if not cfg.get("bot_active_profile"):
            cfg.set("bot_active_profile", name)

    def remove_profile(self, name: str) -> bool:
        cfg = get_config()
        profiles = [p for p in cfg.get("bot_profiles", []) if isinstance(p, dict)]
        kept = [p for p in profiles if p.get("name") != name]
        if len(kept) == len(profiles):
            return False
        cfg.set("bot_profiles", kept)

        if cfg.get("bot_active_profile") == name:
            cfg.set("bot_active_profile", kept[0]["name"] if kept else "")
        return True

    def use_profile(self, name: str) -> None:
        if self.get_profile(name) is None:
            raise ValueError(f"Profile '{name}' not found")
        get_config().set("bot_active_profile", name)

    async def start(self, profile_name: Optional[str] = None) -> BotService:
        profile = self.get_profile(profile_name)
        if profile is None:
            raise ValueError("No active bot profile configured")

        if self._service and self._service.running and self._service.profile_name == profile.name:
            return self._service

        await self.stop()
        service = BotService(profile_name=profile.name, token=profile.token, config_dir=get_config().config_dir)
        await service.start()
        self._service = service
        return service

    async def stop(self) -> None:
        if self._service:
            await self._service.stop()
            self._service = None

    def service(self) -> Optional[BotService]:
        return self._service

    def status(self) -> dict:
        if self._service:
            return self._service.status()
        return {
            "running": False,
            "profile": self.get_active_profile_name() or None,
            "started_at": None,
            "last_poll_ok_at": None,
            "last_error": None,
            "restart_count": 0,
            "loaded_commands": [],
        }


_bot_manager_singleton: Optional[BotManager] = None


def get_bot_manager() -> BotManager:
    global _bot_manager_singleton
    if _bot_manager_singleton is None:
        _bot_manager_singleton = BotManager()
    return _bot_manager_singleton
