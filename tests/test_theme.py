"""
Tests for telegcli.ui.theme

Covers: palette selection, format_ts timezone normalisation (fix #17),
        day-label logic (fix #18), entity_name helpers.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from telegcli.ui.theme import (
    entity_name, entity_type_icon, format_ts, _day_label, get_palette,
)


# ── get_palette ───────────────────────────────────────────────────────────────

def test_get_palette_default_dark():
    with patch("telegcli.ui.theme.get_config") as mock_cfg:
        mock_cfg.return_value.get.return_value = "dark"
        p = get_palette()
    assert p["accent"] == "#7aa2f7"


def test_get_palette_gruvbox():
    with patch("telegcli.ui.theme.get_config") as mock_cfg:
        mock_cfg.return_value.get.return_value = "gruvbox"
        p = get_palette()
    assert p["accent"] == "#83a598"


def test_get_palette_unknown_falls_back_to_dark():
    with patch("telegcli.ui.theme.get_config") as mock_cfg:
        mock_cfg.return_value.get.return_value = "neon_cyberpunk"
        p = get_palette()
    assert p["accent"] == "#7aa2f7"


# ── entity_name ───────────────────────────────────────────────────────────────

def test_entity_name_user_full_name():
    from telethon.tl.types import User
    user = MagicMock(spec=User)
    user.first_name = "John"
    user.last_name = "Doe"
    assert entity_name(user) == "John Doe"


def test_entity_name_user_no_last_name():
    from telethon.tl.types import User
    user = MagicMock(spec=User)
    user.first_name = "Alice"
    user.last_name = None
    assert entity_name(user) == "Alice"


def test_entity_name_user_no_name_uses_id():
    from telethon.tl.types import User
    user = MagicMock(spec=User)
    user.first_name = None
    user.last_name = None
    user.id = 99
    assert entity_name(user) == "99"


def test_entity_name_channel():
    from telethon.tl.types import Channel
    ch = MagicMock(spec=Channel)
    ch.title = "Tech News"
    assert entity_name(ch) == "Tech News"


# ── format_ts timezone normalization (fix #17) ───────────────────────────────

def test_format_ts_none_returns_empty():
    assert format_ts(None) == ""


def test_format_ts_normalizes_to_local_timezone():
    # Create a UTC datetime
    utc_dt = datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    # Get local offset
    local_dt = utc_dt.astimezone()
    expected_hour = local_dt.hour

    with patch("telegcli.ui.theme.get_config") as mock_cfg:
        mock_cfg.return_value.get.return_value = "%H:%M"
        result = format_ts(utc_dt)

    h, m = map(int, result.split(":"))
    assert h == expected_hour


def test_format_ts_uses_config_format():
    dt = datetime(2024, 1, 15, 9, 5, 0, tzinfo=timezone.utc)
    with patch("telegcli.ui.theme.get_config") as mock_cfg:
        mock_cfg.return_value.get.return_value = "%Y-%m-%d"
        result = format_ts(dt)
    # Should contain the year at minimum
    assert "2024" in result


# ── _day_label (fix #18) ─────────────────────────────────────────────────────

def test_day_label_today():
    now = datetime.now(tz=timezone.utc)
    assert _day_label(now) == "Today"


def test_day_label_yesterday():
    yesterday = datetime.now(tz=timezone.utc) - timedelta(days=1)
    assert _day_label(yesterday) == "Yesterday"


def test_day_label_older_date():
    old = datetime(2023, 3, 14, tzinfo=timezone.utc)
    label = _day_label(old)
    assert "2023" in label or "March" in label


# ── entity_type_icon ──────────────────────────────────────────────────────────

def test_entity_type_icon_user():
    from telethon.tl.types import User
    user = MagicMock(spec=User)
    user.bot = False
    assert entity_type_icon(user) == "👤"


def test_entity_type_icon_bot():
    from telethon.tl.types import User
    user = MagicMock(spec=User)
    user.bot = True
    assert entity_type_icon(user) == "🤖"


def test_entity_type_icon_channel_broadcast():
    from telethon.tl.types import Channel
    ch = MagicMock(spec=Channel)
    ch.broadcast = True
    assert entity_type_icon(ch) == "📢"


def test_entity_type_icon_channel_group():
    from telethon.tl.types import Channel
    ch = MagicMock(spec=Channel)
    ch.broadcast = False
    assert entity_type_icon(ch) == "👥"

