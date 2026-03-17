"""
Tests for telegcli.utils.resolver

Covers: index resolution, fuzzy name match, cache write-back (fix #13),
        username resolution, fallback to live search, error output.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── DialogCache ───────────────────────────────────────────────────────────────

from telegcli.utils.resolver import DialogCache


def make_dialog(name: str, entity_id: int):
    dialog = MagicMock()
    dialog.name = name
    dialog.entity = MagicMock()
    dialog.entity.id = entity_id
    return dialog


def test_dialog_cache_by_index():
    cache = DialogCache()
    dialogs = [make_dialog("Alice", 1), make_dialog("Bob", 2)]
    with patch("telegcli.utils.resolver.tg"):
        cache.update(dialogs)
    assert cache.by_index(1).id == 1
    assert cache.by_index(2).id == 2
    assert cache.by_index(3) is None


def test_dialog_cache_by_name_exact():
    cache = DialogCache()
    dialogs = [make_dialog("Alice", 1), make_dialog("Bob", 2)]
    with patch("telegcli.utils.resolver.tg"):
        cache.update(dialogs)
    result = cache.by_name_fuzzy("alice")
    assert result.id == 1


def test_dialog_cache_by_name_prefix():
    cache = DialogCache()
    dialogs = [make_dialog("Alexander", 10)]
    with patch("telegcli.utils.resolver.tg"):
        cache.update(dialogs)
    assert cache.by_name_fuzzy("alex").id == 10


def test_dialog_cache_by_name_substring():
    cache = DialogCache()
    dialogs = [make_dialog("Work Chat", 99)]
    with patch("telegcli.utils.resolver.tg"):
        cache.update(dialogs)
    assert cache.by_name_fuzzy("work").id == 99


def test_dialog_cache_update_writes_to_entity_cache():
    cache = DialogCache()
    entity = MagicMock()
    entity.id = 42
    dialog = MagicMock()
    dialog.name = "Test"
    dialog.entity = entity

    mock_tg = MagicMock()
    with patch("telegcli.utils.resolver.tg", mock_tg):
        cache.update([dialog])

    mock_tg.cache_entity.assert_called_with(entity)


# ── resolve_entity ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_by_index():
    cache = DialogCache()
    entity = MagicMock()
    entity.id = 5
    dialogs = [MagicMock(name="Chat", entity=entity)]
    dialogs[0].name = "Chat"

    with patch("telegcli.utils.resolver.dialog_cache") as mock_cache, \
         patch("telegcli.utils.resolver.tg") as mock_tg:

        mock_cache.by_index.return_value = entity
        mock_tg.cache_entity = MagicMock()

        from telegcli.utils.resolver import resolve_entity
        result = await resolve_entity("1")

    assert result is entity
    mock_tg.cache_entity.assert_called_with(entity)


@pytest.mark.asyncio
async def test_resolve_returns_none_on_not_found():
    with patch("telegcli.utils.resolver.dialog_cache") as mock_cache, \
         patch("telegcli.utils.resolver.tg") as mock_tg, \
         patch("telegcli.utils.resolver.print_error") as mock_err:

        mock_cache.by_index.return_value = None
        mock_cache.by_name_fuzzy.return_value = None
        mock_tg.get_entity = AsyncMock(side_effect=Exception("not found"))
        mock_tg.search_dialogs = AsyncMock(return_value=[])
        mock_tg._entity_cache = {}

        from telegcli.utils.resolver import resolve_entity
        result = await resolve_entity("@nonexistent_user_xyz")

    assert result is None
    mock_err.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_uses_entity_cache_for_numeric_id():
    entity = MagicMock()
    entity.id = 123

    with patch("telegcli.utils.resolver.tg") as mock_tg, \
         patch("telegcli.utils.resolver.dialog_cache") as mock_cache, \
         patch("telegcli.core.client.get_client") as mock_get_client:

        mock_client = MagicMock()
        mock_client._entity_cache = {123: entity}
        mock_get_client.return_value = mock_client
        mock_cache.by_index.return_value = None

        from telegcli.utils.resolver import resolve_entity
        result = await resolve_entity("123")

    # Should be found in entity cache without a network call
    assert result is entity
    mock_tg.get_entity.assert_not_called()
