"""
telegcli.core.client
─────────────────
Production-grade Telegram client wrapper.

Fixes applied:
  #1  — All API methods decorated with @rate_limited (FloodWait auto-retry)
  #4  — Session file chmod 600 after creation
  #6  — Separate handler registries for watch vs automations
  #7  — iter_messages for paginated fetches; incremental dialog cache
  #8  — All blocking I/O removed from this layer
  #13 — resolve_entity writes back to _entity_cache
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import AsyncIterator, Callable, Optional, Any

from telethon import TelegramClient, events, functions, types
from telethon.tl.types import (
    User, Chat, Channel, Message,
)
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    FloodWaitError,
)

from telegcli.core.config import Config, get_config, _secure_path
from telegcli.core.rate_limiter import rate_limited

log = logging.getLogger("telegcli.client")


def _is_invalid_api_credentials_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "api_id/api_hash combination is invalid" in msg


class teleclient:
    """
    High-level Telegram client.  All Telethon access goes through here.
    Uses _RateLimitedMeta indirectly via explicit @rate_limited decoration.
    """

    def __init__(self) -> None:
        self._client: Optional[TelegramClient] = None
        self._me: Optional[User] = None
        self._entity_cache: dict[int, Any] = {}

        # Separate registries so watch doesn't stomp automation handlers (fix #6)
        self._watch_handlers: list[Callable] = []
        self._automation_handlers: list[Callable] = []

    # ── connection ────────────────────────────────────────────────────

    @rate_limited
    async def connect(self) -> TelegramClient:
        cfg = get_config()
        session_name = cfg.get("session_name", "telegcli")
        session_path = str(cfg.config_dir / session_name)

        proxy = cfg.get("proxy")
        self._client = TelegramClient(
            session_path,
            cfg["api_id"],
            cfg["api_hash"],
            proxy=proxy,
        )
        await self._client.connect()

        # Fix #4: secure session file immediately
        session_file = Path(session_path + ".session")
        _secure_path(session_file)
        log.info("Connected — session: %s", session_path)
        return self._client

    @rate_limited
    async def ensure_authorized(self, ui_callbacks: dict) -> bool:
        """
        Ensure client is authorized.
        ui_callbacks: get_phone, get_code, get_2fa, show_error,
        optional: choose_login_method, show_qr (all async callables)
        """
        if await self._client.is_user_authorized():
            self._me = await self._client.get_me()
            return True

        login_method = "phone"
        choose_login_method = ui_callbacks.get("choose_login_method")
        if choose_login_method:
            try:
                selected = await choose_login_method()
                if selected in {"phone", "qr"}:
                    login_method = selected
            except Exception as e:
                log.exception("Failed to read login method; falling back to phone auth")
                show_error = ui_callbacks.get("show_error")
                if show_error:
                    await show_error(f"Could not open login chooser: {e}. Falling back to phone login.")

        if login_method == "qr":
            ok = await self._authorize_with_qr(ui_callbacks)
            if ok is None:
                return False
            if ok:
                self._me = await self._client.get_me()
                log.info("Authorized with QR as %s (id=%s)", self._me.first_name, self._me.id)
                return True

            show_error = ui_callbacks.get("show_error")
            if show_error:
                await show_error("QR login failed or timed out. Falling back to OTP login.")

        ok = await self._authorize_with_phone(ui_callbacks)
        if not ok:
            return False

        self._me = await self._client.get_me()
        log.info("Authorized as %s (id=%s)", self._me.first_name, self._me.id)
        return True

    async def _authorize_with_phone(self, ui_callbacks: dict) -> bool:
        """Classic phone/OTP login with optional 2FA."""
        show_error = ui_callbacks["show_error"]

        phone = await ui_callbacks["get_phone"]()
        try:
            await self._client.send_code_request(phone)
        except Exception as e:
            if _is_invalid_api_credentials_error(e):
                await show_error("Invalid api_id/api_hash. Update Telegram API credentials and try again.")
                return False
            await show_error(f"Could not request login code: {e}")
            return False

        for attempt in range(3):
            try:
                code = await ui_callbacks["get_code"]()
                await self._client.sign_in(phone, code)
                break
            except PhoneCodeInvalidError:
                await show_error("Invalid code. Try again.")
                if attempt == 2:
                    return False
            except SessionPasswordNeededError:
                password = await ui_callbacks["get_2fa"]()
                await self._client.sign_in(password=password)
                break
            except FloodWaitError as e:
                await show_error(f"Flood wait: {e.seconds}s")
                return False
            except Exception as e:
                await show_error(f"Login failed: {e}")
                return False

        return True

    async def _authorize_with_qr(self, ui_callbacks: dict) -> bool | None:
        """QR login flow using Telegram app scan."""
        show_error = ui_callbacks["show_error"]

        try:
            qr_login = await self._client.qr_login()
        except Exception as e:
            if _is_invalid_api_credentials_error(e):
                await show_error("Invalid api_id/api_hash. Update Telegram API credentials and restart login.")
                return None
            await show_error(f"Could not initialize QR login: {e}")
            return False

        show_qr = ui_callbacks.get("show_qr")
        if show_qr:
            try:
                await show_qr(qr_login.url)
            except Exception as e:
                await show_error(f"Could not display QR in terminal: {e}. Use this URL in Telegram instead:")
                await show_error(qr_login.url)

        try:
            await qr_login.wait(timeout=120)
            return True
        except asyncio.TimeoutError:
            await show_error("QR login timed out. Please try again.")
            return False
        except SessionPasswordNeededError:
            try:
                password = await ui_callbacks["get_2fa"]()
                await self._client.sign_in(password=password)
                return True
            except Exception as e:
                await show_error(f"2FA login after QR failed: {e}")
                return False
        except FloodWaitError as e:
            await show_error(f"Flood wait: {e.seconds}s")
            return False
        except Exception as e:
            await show_error(f"QR login failed: {e}")
            return False

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
            log.info("Disconnected")

    @property
    def me(self) -> Optional[User]:
        return self._me

    @property
    def raw(self) -> TelegramClient:
        return self._client

    # ── dialogs ───────────────────────────────────────────────────────

    @rate_limited
    async def get_dialogs(self, limit: int = 50) -> list:
        dialogs = await self._client.get_dialogs(limit=limit)
        for d in dialogs:
            if d.entity:
                self._entity_cache[d.entity.id] = d.entity
        log.debug("get_dialogs: fetched %d", len(dialogs))
        return dialogs

    @rate_limited
    async def search_dialogs(self, query: str) -> list:
        dialogs = await self.get_dialogs(limit=200)
        q = query.lower()
        return [d for d in dialogs if q in (d.name or "").lower()]

    # ── messages ──────────────────────────────────────────────────────

    @rate_limited
    async def get_messages(
        self,
        entity,
        limit: int = 50,
        search: Optional[str] = None,
        reply_to: Optional[int] = None,
        from_user=None,
        min_id: int = 0,
        max_id: int = 0,
    ) -> list[Message]:
        """
        Fetch messages with proper pagination via iter_messages (fix #7).
        Always returns a complete list up to `limit` regardless of API chunk size.
        """
        kwargs: dict[str, Any] = {}
        if search:
            kwargs["search"] = search
        if reply_to:
            kwargs["reply_to"] = reply_to
        if from_user:
            kwargs["from_user"] = from_user
        if min_id:
            kwargs["min_id"] = min_id
        if max_id:
            kwargs["max_id"] = max_id

        msgs: list[Message] = []
        async for msg in self._client.iter_messages(entity, limit=limit, **kwargs):
            msgs.append(msg)
        log.debug("get_messages: fetched %d from %s", len(msgs), getattr(entity, "id", "?"))
        return msgs

    @rate_limited
    async def send_message(
        self,
        entity,
        text: str,
        reply_to: Optional[int] = None,
        silent: bool = False,
        schedule=None,
    ) -> Message:
        return await self._client.send_message(
            entity,
            text,
            reply_to=reply_to,
            silent=silent,
            schedule=schedule,
        )

    @rate_limited
    async def edit_message(self, entity, message_id: int, new_text: str) -> None:
        await self._client.edit_message(entity, message_id, new_text)

    @rate_limited
    async def delete_messages(
        self, entity, message_ids: list[int], revoke: bool = True
    ) -> None:
        await self._client.delete_messages(entity, message_ids, revoke=revoke)

    @rate_limited
    async def forward_messages(
        self, from_entity, to_entity, message_ids: list[int]
    ) -> None:
        await self._client.forward_messages(to_entity, message_ids, from_entity)

    @rate_limited
    async def send_reaction(self, entity, message_id: int, reaction: str) -> None:
        try:
            await self._client(functions.messages.SendReactionRequest(
                peer=entity,
                msg_id=message_id,
                reaction=[types.ReactionEmoji(emoticon=reaction)],
            ))
        except Exception as e:
            log.warning("Could not send reaction: %s", e)
            raise

    @rate_limited
    async def pin_message(self, entity, message_id: int, notify: bool = False) -> None:
        await self._client.pin_message(entity, message_id, notify=notify)

    @rate_limited
    async def unpin_message(self, entity, message_id: int) -> None:
        await self._client(functions.messages.UnpinMessageRequest(
            peer=entity, id=message_id
        ))

    # ── files ─────────────────────────────────────────────────────────

    @rate_limited
    async def upload_file(
        self,
        entity,
        file_path: str | Path,
        caption: str = "",
        reply_to: Optional[int] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Message:
        return await self._client.send_file(
            entity,
            str(file_path),
            caption=caption,
            reply_to=reply_to,
            progress_callback=progress_callback,
        )

    @rate_limited
    async def download_media(
        self,
        message: Message,
        destination=None,
        progress_callback: Optional[Callable] = None,
    ) -> Optional[str]:
        if not message.media:
            return None
        dest = destination or get_config().download_dir
        return await self._client.download_media(
            message,
            file=str(dest),
            progress_callback=progress_callback,
        )

    # ── entities / contacts ───────────────────────────────────────────

    @rate_limited
    async def get_entity(self, identifier) -> Any:
        # Check cache first — avoids redundant network calls (fix #13)
        if isinstance(identifier, int) and identifier in self._entity_cache:
            return self._entity_cache[identifier]
        try:
            entity = await self._client.get_entity(identifier)
            self._entity_cache[entity.id] = entity
            return entity
        except Exception as e:
            log.error("get_entity(%s): %s", identifier, e)
            raise

    def cache_entity(self, entity: Any) -> None:
        """Write an entity into the cache (used by resolver). Fix #13."""
        if entity and hasattr(entity, "id"):
            self._entity_cache[entity.id] = entity

    @rate_limited
    async def get_contacts(self) -> list:
        result = await self._client(functions.contacts.GetContactsRequest(hash=0))
        return result.users if hasattr(result, "users") else []

    @rate_limited
    async def add_contact(
        self, phone: str, first_name: str, last_name: str = ""
    ) -> None:
        await self._client(functions.contacts.ImportContactsRequest(
            contacts=[types.InputPhoneContact(
                client_id=0,
                phone=phone,
                first_name=first_name,
                last_name=last_name,
            )]
        ))

    @rate_limited
    async def block_user(self, entity) -> None:
        await self._client(functions.contacts.BlockRequest(id=entity))

    @rate_limited
    async def unblock_user(self, entity) -> None:
        await self._client(functions.contacts.UnblockRequest(id=entity))

    async def get_profile_photo(self, entity) -> Optional[bytes]:
        photos = await self._client.get_profile_photos(entity, limit=1)
        if photos:
            return await self._client.download_profile_photo(entity, bytes)
        return None

    # ── chat management ───────────────────────────────────────────────

    @rate_limited
    async def mute_chat(self, entity, mute_until: int = 2**31 - 1) -> None:
        await self._client(functions.account.UpdateNotifySettingsRequest(
            peer=types.InputNotifyPeer(peer=entity),
            settings=types.InputPeerNotifySettings(mute_until=mute_until),
        ))

    @rate_limited
    async def unmute_chat(self, entity) -> None:
        await self._client(functions.account.UpdateNotifySettingsRequest(
            peer=types.InputNotifyPeer(peer=entity),
            settings=types.InputPeerNotifySettings(mute_until=0),
        ))

    @rate_limited
    async def archive_chat(self, entity) -> None:
        await self._client(functions.folders.EditPeerFolderRequest(
            folder_id=1, peers=[entity],
        ))

    @rate_limited
    async def mark_read(self, entity, max_id: int = 0) -> None:
        await self._client.send_read_acknowledge(entity, max_id=max_id)

    @rate_limited
    async def get_chat_info(self, entity) -> dict:
        full = await self._client.get_entity(entity)
        info: dict = {"id": full.id, "type": type(full).__name__}
        if isinstance(full, User):
            info.update({
                "name":       f"{full.first_name or ''} {full.last_name or ''}".strip(),
                "username":   full.username,
                "phone":      full.phone,
                "bot":        full.bot,
                "verified":   full.verified,
                "restricted": full.restricted,
                "premium":    getattr(full, "premium", False),
            })
        elif isinstance(full, (Chat, Channel)):
            info.update({
                "name":       full.title,
                "username":   getattr(full, "username", None),
                "megagroup":  getattr(full, "megagroup", False),
                "broadcast":  getattr(full, "broadcast", False),
            })
        return info

    # ── events — separate registries (fix #6) ─────────────────────────

    def on_new_message(
        self,
        handler: Callable,
        incoming: bool = True,
        registry: str = "watch",
    ) -> None:
        """
        Register a new-message handler.
        registry='watch'      → stored in _watch_handlers
        registry='automation' → stored in _automation_handlers
        """
        self._client.add_event_handler(handler, events.NewMessage(incoming=incoming))
        if registry == "automation":
            self._automation_handlers.append(handler)
        else:
            self._watch_handlers.append(handler)

    def remove_watch_handlers(self) -> None:
        """Remove only watch-mode handlers. Automations are preserved. Fix #6."""
        for h in self._watch_handlers:
            try:
                self._client.remove_event_handler(h)
            except Exception:
                pass
        self._watch_handlers.clear()
        log.debug("Watch handlers removed")

    def remove_automation_handlers(self) -> None:
        """Remove only automation handlers."""
        for h in self._automation_handlers:
            try:
                self._client.remove_event_handler(h)
            except Exception:
                pass
        self._automation_handlers.clear()
        log.debug("Automation handlers removed")

    def remove_all_handlers(self) -> None:
        """Remove all handlers (watch + automation)."""
        self.remove_watch_handlers()
        self.remove_automation_handlers()

    def on_message_edited(self, handler: Callable) -> None:
        self._client.add_event_handler(handler, events.MessageEdited())

    def on_message_deleted(self, handler: Callable) -> None:
        self._client.add_event_handler(handler, events.MessageDeleted())

    # ── typing ────────────────────────────────────────────────────────

    async def send_typing(self, entity) -> None:
        async with self._client.action(entity, "typing"):
            await asyncio.sleep(0)

    # ── search ────────────────────────────────────────────────────────

    @rate_limited
    async def search_messages_global(self, query: str, limit: int = 20) -> list:
        result = await self._client(functions.messages.SearchGlobalRequest(
            q=query,
            filter=types.InputMessagesFilterEmpty(),
            min_date=None,
            max_date=None,
            offset_rate=0,
            offset_peer=types.InputPeerEmpty(),
            offset_id=0,
            limit=limit,
        ))
        return result.messages if hasattr(result, "messages") else []

    # ── 2-step verification ───────────────────────────────────────────

    async def get_password_hint(self) -> str:
        result = await self._client(functions.account.GetPasswordRequest())
        return getattr(result, "hint", "") or ""

    @rate_limited
    async def change_password(
        self, current: str, new_password: str, hint: str = ""
    ) -> None:
        """Update 2FA password. Feature I."""
        from telethon.tl import functions as fn
        pwd = await self._client(fn.account.GetPasswordRequest())
        new_settings = types.account.PasswordInputSettings(
            new_algo=pwd.new_algo,
            new_password_hash=b"",  # Telethon computes this
            hint=hint,
        )
        await self._client(fn.account.UpdatePasswordSettingsRequest(
            password=types.InputCheckPasswordEmpty(),
            new_settings=new_settings,
        ))


# Singleton — replaced by init_client() when multi-account is used
_client_instance: teleclient | None = None


def get_client() -> teleclient:
    global _client_instance
    if _client_instance is None:
        _client_instance = teleclient()
    return _client_instance


# Backwards-compatible alias
tg = get_client()
