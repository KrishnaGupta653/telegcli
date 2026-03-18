"""
telegcli.core.rate_limiter
────────────────────────
Centralised async rate-limit + retry wrapper.

Fix #1: catches FloodWaitError everywhere, waits e.seconds, retries
transparently so no command ever crashes with a raw Telegram traceback.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable, TypeVar

from telethon.errors import (
    FloodWaitError,
    ServerError,
    BadRequestError,
    AuthKeyError,
    RPCError,
)

from telegcli.ui.theme import print_warning

log = logging.getLogger("telegcli.rate_limiter")

F = TypeVar("F", bound=Callable[..., Any])

_RETRYABLE = (FloodWaitError, ServerError)


def _get_max_retries() -> int:
    """Get max API retries from config or default to 3."""
    try:
        from telegcli.core.config import get_config
        return int(get_config().get("max_api_retries", 3))
    except Exception:
        return 3


def rate_limited(func: F) -> F:
    """
    Decorator: wraps an async method on teleclient so that:
      - FloodWaitError  → waits e.seconds (+ 1s buffer) then retries
      - ServerError     → waits 5 s then retries (up to MAX_RETRIES)
      - Other RPCError  → re-raises with a clean message (no traceback spam)
      - AuthKeyError    → re-raises immediately (session is toast)
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        max_retries = _get_max_retries()
        attempt = 0
        while True:
            try:
                return await func(*args, **kwargs)
            except FloodWaitError as e:
                wait = e.seconds + 1
                log.warning(
                    "FloodWaitError in %s — waiting %ds (attempt %d/%d)",
                    func.__name__, wait, attempt + 1, max_retries,
                )
                print_warning(
                    f"Telegram rate limit — waiting {wait}s before retrying…"
                )
                await asyncio.sleep(wait)
                attempt += 1
                if attempt >= max_retries:
                    raise
            except ServerError as e:
                wait = 5
                attempt += 1
                log.warning(
                    "Telegram ServerError in %s: %s — retry %d/%d in %ds",
                    func.__name__, e, attempt, max_retries, wait,
                )
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(wait)
            except AuthKeyError:
                log.error("AuthKeyError — session is invalid")
                raise
            except BadRequestError as e:
                # Don't retry bad-request errors — they won't succeed on retry
                log.debug("BadRequestError in %s: %s", func.__name__, e)
                raise
            except RPCError as e:
                log.error("RPCError in %s: %s", func.__name__, e)
                raise
    return wrapper  # type: ignore[return-value]


class _RateLimitedMeta(type):
    """
    Metaclass that auto-applies @rate_limited to every async method
    whose name starts with a verb (get_, send_, upload_, download_,
    search_, add_, edit_, delete_, forward_, pin_, etc.)
    """
    _PREFIX = (
        "get_", "send_", "upload_", "download_", "search_",
        "add_", "edit_", "delete_", "forward_", "pin_", "unpin_",
        "block_", "unblock_", "mute_", "unmute_", "archive_",
        "mark_", "ensure_", "connect",
    )

    def __new__(mcs, name: str, bases: tuple, namespace: dict) -> type:
        for attr, val in list(namespace.items()):
            if (
                asyncio.iscoroutinefunction(val)
                and any(attr.startswith(p) for p in mcs._PREFIX)
                and not getattr(val, "_rate_limited", False)
            ):
                wrapped = rate_limited(val)
                wrapped._rate_limited = True  # type: ignore[attr-defined]
                namespace[attr] = wrapped
        return super().__new__(mcs, name, bases, namespace)
