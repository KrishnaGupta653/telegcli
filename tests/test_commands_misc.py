"""
Tests for misc commands: template, draft, automate add/remove.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


@pytest.fixture
def mock_config(tmp_path):
    from telegcli.core.config import Config
    cfg = Config(config_dir=tmp_path)
    return cfg


# ── template ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_template_save_and_list(mock_config):
    with patch("telegcli.commands.misc.get_config", return_value=mock_config), \
         patch("telegcli.commands.misc.get_console") as mock_console, \
         patch("telegcli.commands.misc.get_palette", return_value={k: "" for k in ["accent","fg","dim","accent2","separator"]}):

        from telegcli.commands.misc import cmd_template
        mock_console.return_value = MagicMock()

        await cmd_template(["save", "greeting", "Hello", "there!"])
        templates = mock_config.get("templates", {})
        assert "greeting" in templates
        assert templates["greeting"] == "Hello there!"


@pytest.mark.asyncio
async def test_template_delete(mock_config):
    mock_config.set("templates", {"greeting": "Hello"})

    with patch("telegcli.commands.misc.get_config", return_value=mock_config), \
         patch("telegcli.commands.misc.get_console") as mock_console, \
         patch("telegcli.commands.misc.get_palette", return_value={k: "" for k in ["accent","fg","dim","accent2","separator"]}), \
         patch("telegcli.commands.misc.print_success"):

        from telegcli.commands.misc import cmd_template
        mock_console.return_value = MagicMock()

        await cmd_template(["delete", "greeting"])

    assert "greeting" not in mock_config.get("templates", {})


# ── draft ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_draft_save(mock_config):
    with patch("telegcli.commands.misc.get_config", return_value=mock_config), \
         patch("telegcli.commands.misc.get_console") as mock_console, \
         patch("telegcli.commands.misc.get_palette", return_value={k: "" for k in ["accent","fg","dim","accent2","separator","timestamp"]}), \
         patch("telegcli.commands.misc.print_success"):

        from telegcli.commands.misc import cmd_draft
        mock_console.return_value = MagicMock()
        await cmd_draft(["save", "@friend", "Draft", "message"])

    drafts = mock_config.get("drafts", [])
    assert len(drafts) == 1
    assert drafts[0]["chat"] == "@friend"
    assert drafts[0]["text"] == "Draft message"


@pytest.mark.asyncio
async def test_draft_delete(mock_config):
    mock_config.set("drafts", [{"id": 1, "chat": "@x", "text": "hi", "saved_at": ""}])

    with patch("telegcli.commands.misc.get_config", return_value=mock_config), \
         patch("telegcli.commands.misc.get_console") as mock_console, \
         patch("telegcli.commands.misc.get_palette", return_value={k: "" for k in ["accent","fg","dim","accent2","separator","timestamp"]}), \
         patch("telegcli.commands.misc.print_success"):

        from telegcli.commands.misc import cmd_draft
        mock_console.return_value = MagicMock()
        await cmd_draft(["delete", "1"])

    assert mock_config.get("drafts") == []


# ── automate remove ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_automate_remove(mock_config):
    mock_config.set("automations", [
        {"trigger": "a", "reply": "1", "enabled": True},
        {"trigger": "b", "reply": "2", "enabled": True},
    ])

    with patch("telegcli.commands.misc.get_config", return_value=mock_config), \
         patch("telegcli.commands.misc.get_console") as mock_console, \
         patch("telegcli.commands.misc.get_palette", return_value={k: "" for k in ["accent","fg","dim","accent2"]}), \
         patch("telegcli.commands.misc.print_success"), \
         patch("telegcli.commands.misc.automation_engine") as mock_engine:

        mock_console.return_value = MagicMock()
        from telegcli.commands.misc import cmd_automate
        await cmd_automate(["remove", "1"])

    rules = mock_config.get("automations", [])
    assert len(rules) == 1
    assert rules[0]["trigger"] == "b"


@pytest.mark.asyncio
async def test_automate_add_with_options(mock_config):
    mock_config.set("automations", [])

    with patch("telegcli.commands.misc.get_config", return_value=mock_config), \
         patch("telegcli.commands.misc.get_console") as mock_console, \
         patch("telegcli.commands.misc.get_palette", return_value={k: "" for k in ["accent","fg","dim","accent2"]}), \
         patch("telegcli.commands.misc.print_success"), \
         patch("telegcli.commands.misc.automation_engine") as mock_engine:

        mock_console.return_value = MagicMock()
        from telegcli.commands.misc import cmd_automate
        await cmd_automate([
            "add", "hello", "hi there",
            "--private", "--limit", "3"
        ])

    rules = mock_config.get("automations", [])
    assert rules[0]["only_private"] is True
    assert rules[0]["max_fires_per_hour"] == 3
    assert rules[0]["reply"] == "hi there"
