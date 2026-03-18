"""
telegcli.utils.resolver
─────────────────────
Resolves human-readable identifiers to Telethon entities.

Fix #13: resolved entities are written back into tg._entity_cache
         so repeat lookups of the same entity are fully local.

Supports:
  - Index number from last `list` output  (e.g. "3")
  - Exact username                         (e.g. "@durov")
  - Fuzzy name match from dialog cache     (e.g. "saved")
  - Phone number                           (e.g. "+91...")
  - Numeric user/chat ID                   (e.g. "123456789")
"""

from __future__ import annotations

import logging
from typing import Optional, Any

from telegcli.core.client import tg
from telegcli.ui.theme import print_error

log = logging.getLogger("telegcli.resolver")


class DialogCache:
    """Stores the last fetched list of dialogs for fast local resolution."""

    def __init__(self) -> None:
        self._dialogs: list = []
        self._by_name: dict[str, Any] = {}

    def update(self, dialogs: list) -> None:
        self._dialogs = dialogs
        self._by_name = {
            (d.name or "").lower(): d.entity
            for d in dialogs
            if d.entity
        }
        # Write everything into the client entity cache (fix #13)
        for d in dialogs:
            if d.entity:
                tg.cache_entity(d.entity)

    def by_index(self, idx: int) -> Optional[Any]:
        """1-based index."""
        if 1 <= idx <= len(self._dialogs):
            return self._dialogs[idx - 1].entity
        return None

    def by_name_fuzzy(self, query: str) -> Optional[Any]:
        q = query.lower()
        if q in self._by_name:
            return self._by_name[q]
        for name, entity in self._by_name.items():
            if name.startswith(q):
                return entity
        for name, entity in self._by_name.items():
            if q in name:
                return entity
        return None

    @property
    def names(self) -> list[str]:
        return list(self._by_name.keys())


dialog_cache = DialogCache()


async def resolve_entity(identifier: str) -> Optional[Any]:
    """
    Resolve an identifier string to a Telethon entity.
    Returns None and prints an error if not found.
    """
    identifier = identifier.strip()

    # 1. Numeric index (from list output)
    if identifier.isdigit():
        idx = int(identifier)
        entity = dialog_cache.by_index(idx)
        if entity:
            tg.cache_entity(entity)  # fix #13
            return entity
        # Help user if dialog cache is empty
        if not dialog_cache._dialogs:
            print_error(
                "No cached dialogs. Run [bold]list[/] first to load chats, "
                "or use @username / phone number directly."
            )
            return None

    # 2. Try client entity cache first — avoids network round-trip (fix #13)
    if identifier.lstrip("-").isdigit():
        uid = int(identifier)
        from telegcli.core.client import get_client
        cached = get_client()._entity_cache.get(uid)
        if cached:
            return cached

    # 3. Fuzzy name match in dialog cache
    if not identifier.startswith("+") and not identifier.lstrip("-").isdigit():
        username = identifier.lstrip("@")
        cached = dialog_cache.by_name_fuzzy(username)
        if cached:
            tg.cache_entity(cached)
            return cached

    # 4. Telethon resolution (handles usernames, phone numbers, IDs)
    try:
        if identifier.lstrip("-").isdigit():
            entity = await tg.get_entity(int(identifier))
        else:
            username = identifier.lstrip("@")
            probe = f"@{username}" if "+" not in identifier else identifier
            entity = await tg.get_entity(probe)
        tg.cache_entity(entity)  # fix #13
        return entity
    except Exception as exc:
        log.debug("Direct entity lookup failed for %r: %s", identifier, exc)

    # 5. Fuzzy fallback against full dialog list
    cached = dialog_cache.by_name_fuzzy(identifier)
    if cached:
        tg.cache_entity(cached)
        return cached

    # 6. Live search as last resort
    try:
        results = await tg.search_dialogs(identifier)
        if results:
            entity = results[0].entity
            tg.cache_entity(entity)
            return entity
    except Exception as exc:
        log.debug("Dialog search failed: %s", exc)

    print_error(
        f"Could not find chat: '{identifier}'\n"
        f"  Run [bold]list[/] to see chats, or use @username / phone number."
    )
    return None
