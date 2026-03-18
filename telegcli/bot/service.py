"""Bot service runtime using Telegram Bot API polling."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import logging
import time
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import httpx

log = logging.getLogger("telegcli.bot.service")

Handler = Callable[["BotContext", list[str]], Any]


@dataclass
class BotContext:
    service: "BotService"
    message: dict[str, Any]
    chat_id: int
    user_id: Optional[int]
    text: str

    async def reply(self, text: str) -> bool:
        return await self.service.send_text(self.chat_id, text)


class BotRouter:
    def __init__(self, service: "BotService") -> None:
        self._service = service
        self._commands: dict[str, tuple[Handler, str]] = {}
        self._default_handler: Optional[Handler] = None
        self._register_builtin()

    def command(self, name: str, handler: Handler, help_text: str = "") -> None:
        self._commands[name.lower()] = (handler, help_text)

    def set_default(self, handler: Handler) -> None:
        self._default_handler = handler

    def list_commands(self) -> list[tuple[str, str]]:
        return sorted([(k, v[1]) for k, v in self._commands.items()], key=lambda x: x[0])

    async def dispatch_message(self, message: dict[str, Any]) -> None:
        text = (message.get("text") or "").strip()
        if not text:
            return

        chat = message.get("chat") or {}
        from_user = message.get("from") or {}
        ctx = BotContext(
            service=self._service,
            message=message,
            chat_id=int(chat.get("id")),
            user_id=from_user.get("id"),
            text=text,
        )

        if text.startswith("/"):
            parts = text.split()
            cmd = parts[0][1:].split("@")[0].lower()
            args = parts[1:]
            target = self._commands.get(cmd)
            if target:
                await _call_handler(target[0], ctx, args)
                return

        if self._default_handler:
            await _call_handler(self._default_handler, ctx, [])

    def _register_builtin(self) -> None:
        async def _start(ctx: BotContext, args: list[str]) -> None:
            await ctx.reply("Bot is running. Use /help to see commands.")

        async def _help(ctx: BotContext, args: list[str]) -> None:
            rows = [f"/{name} - {help_text}" for name, help_text in self.list_commands() if help_text]
            if not rows:
                rows = ["No commands registered."]
            await ctx.reply("Available commands:\n" + "\n".join(rows))

        async def _ping(ctx: BotContext, args: list[str]) -> None:
            await ctx.reply("pong")

        self.command("start", _start, "Show bot startup message")
        self.command("help", _help, "List commands")
        self.command("ping", _ping, "Health check")


async def _call_handler(handler: Handler, ctx: BotContext, args: list[str]) -> None:
    result = handler(ctx, args)
    if inspect.isawaitable(result):
        await result


class BotService:
    def __init__(self, profile_name: str, token: str, config_dir: Path) -> None:
        self.profile_name = profile_name
        self.token = token
        self.config_dir = config_dir

        self.router = BotRouter(self)

        self._offset = 0
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None

        self._logs: deque[str] = deque(maxlen=500)
        self.started_at: Optional[float] = None
        self.last_poll_ok_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.restart_count: int = 0

        # Hot reload support
        self._plugin_watch_task: Optional[asyncio.Task] = None
        self._plugin_file_mtimes: dict[Path, float] = {}  # Track file modification times
        self._loaded_plugins: dict[str, Any] = {}  # Track loaded modules for unloading

    @property
    def running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def log_event(self, msg: str) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        self._logs.append(line)
        log.info("bot[%s] %s", self.profile_name, msg)

    def get_logs(self, n: int = 50) -> list[str]:
        n = max(1, min(500, n))
        return list(self._logs)[-n:]

    def status(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name,
            "running": self.running,
            "started_at": self.started_at,
            "last_poll_ok_at": self.last_poll_ok_at,
            "last_error": self.last_error,
            "restart_count": self.restart_count,
            "loaded_commands": [name for name, _ in self.router.list_commands()],
        }

    async def start(self) -> None:
        if self.running:
            return

        try:
            self._running = True
            self.started_at = time.time()
            self.last_error = None
            self._offset = 0
            self._client = httpx.AsyncClient(timeout=40.0)
            self._load_plugins()
            self._task = asyncio.create_task(self._run_poll_loop(), name=f"bot-poll-{self.profile_name}")
            self._plugin_watch_task = asyncio.create_task(self._run_plugin_watch_loop(), name=f"bot-watch-{self.profile_name}")
            self.log_event("service started")
        except Exception as e:
            self._running = False
            self.last_error = str(e)
            log.error("Failed to start bot service: %s", e, exc_info=True)
            await self.cleanup()
            raise

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        
        if self._plugin_watch_task and not self._plugin_watch_task.done():
            self._plugin_watch_task.cancel()
            try:
                await self._plugin_watch_task
            except asyncio.CancelledError:
                pass
        self._plugin_watch_task = None
        
        await self.cleanup()
        self.log_event("service stopped")

    async def cleanup(self) -> None:
        """Clean up resources (client, files, etc.)."""
        if self._client:
            try:
                await self._client.aclose()
            except Exception as e:
                log.debug("Error closing HTTP client: %s", e)
            self._client = None

    async def send_text(self, chat_id: int, text: str) -> bool:
        try:
            await self._api("sendMessage", {"chat_id": chat_id, "text": text})
            return True
        except Exception as e:
            self.last_error = str(e)
            self.log_event(f"send message failed: {e}")
            return False

    async def _run_poll_loop(self) -> None:
        backoff = 1
        while self._running:
            try:
                updates = await self._api("getUpdates", {
                    "timeout": 25,
                    "offset": self._offset,
                    "allowed_updates": ["message", "edited_message"],
                })
                self.last_poll_ok_at = time.time()
                self.last_error = None
                backoff = 1

                for upd in updates:
                    upd_id = int(upd.get("update_id", 0))
                    if upd_id >= self._offset:
                        self._offset = upd_id + 1

                    message = upd.get("message") or upd.get("edited_message")
                    if message:
                        await self.router.dispatch_message(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_error = str(e)
                self.restart_count += 1
                self.log_event(f"poll error: {e}; retry in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _api(self, method: str, payload: Optional[dict[str, Any]] = None) -> Any:
        if not self._client:
            raise RuntimeError("Bot client is not initialized")

        url = f"https://api.telegram.org/bot{self.token}/{method}"
        resp = await self._client.post(url, json=payload or {})
        resp.raise_for_status()

        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description", "Telegram Bot API returned error"))
        return data.get("result")

    def _load_plugins(self) -> None:
        plugin_dir = self.config_dir / "bots" / self.profile_name / "plugins"
        if not plugin_dir.exists():
            return

        for file_path in sorted(plugin_dir.glob("*.py")):
            try:
                mod_name = f"telegcli_bot_plugin_{self.profile_name}_{file_path.stem}"
                spec = importlib.util.spec_from_file_location(mod_name, file_path)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                register = getattr(module, "register", None)
                if callable(register):
                    register(self.router)
                    self.log_event(f"plugin loaded: {file_path.name}")
                    self._loaded_plugins[str(file_path)] = module
                    self._plugin_file_mtimes[file_path] = file_path.stat().st_mtime
            except Exception as e:
                self.log_event(f"plugin load failed ({file_path.name}): {e}")

    async def _run_plugin_watch_loop(self) -> None:
        """
        Watch plugin directory for changes and hot-reload plugins.
        Runs continuously looking for file modifications.
        """
        plugin_dir = self.config_dir / "bots" / self.profile_name / "plugins"
        
        while self._running:
            try:
                if not plugin_dir.exists():
                    await asyncio.sleep(2)
                    continue

                # Check all Python files in plugin directory
                for file_path in plugin_dir.glob("*.py"):
                    try:
                        current_mtime = file_path.stat().st_mtime
                        last_mtime = self._plugin_file_mtimes.get(file_path, 0)

                        # File was modified
                        if current_mtime > last_mtime:
                            self.log_event(f"plugin changed: {file_path.name} — reloading")
                            await self._reload_plugin(file_path)
                            self._plugin_file_mtimes[file_path] = current_mtime

                    except Exception as e:
                        self.log_event(f"plugin watch error ({file_path.name}): {e}")

                # Sleep before next check
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log_event(f"plugin watch loop error: {e}")
                await asyncio.sleep(2)

    async def _reload_plugin(self, file_path: Path) -> None:
        """
        Reload a single plugin file.
        Unloads old commands and loads new ones.
        """
        try:
            mod_name = f"telegcli_bot_plugin_{self.profile_name}_{file_path.stem}"

            # Unload old module from sys.modules if it exists
            if mod_name in sys.modules:
                del sys.modules[mod_name]

            # Load new module
            spec = importlib.util.spec_from_file_location(mod_name, file_path)
            if spec is None or spec.loader is None:
                self.log_event(f"plugin reload failed ({file_path.name}): invalid spec")
                return

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Call register function
            register = getattr(module, "register", None)
            if callable(register):
                # Create a fresh router context for reloading
                register(self.router)
                self.log_event(f"plugin reloaded: {file_path.name}")
                self._loaded_plugins[str(file_path)] = module
            else:
                self.log_event(f"plugin reload failed ({file_path.name}): no register function")

        except Exception as e:
            self.log_event(f"plugin reload failed ({file_path.name}): {e}")
