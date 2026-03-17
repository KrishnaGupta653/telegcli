"""
Tests for telegcli.core.config

Covers: schema migration, type coercion, deep-merge, secure permissions,
        session_name override, reset, validation clamping.
"""

import json
import os
import stat
import sys
import tempfile
from pathlib import Path

import pytest

from telegcli.core.config import (
    Config, _deep_merge, _migrate, _validate, _coerce,
    DEFAULTS, CURRENT_SCHEMA_VERSION,
)


# ── _deep_merge ───────────────────────────────────────────────────────────────

def test_deep_merge_fills_missing_keys():
    base = {"a": 1, "nested": {"x": 1, "y": 2}}
    override = {"nested": {"x": 99}}
    result = _deep_merge(base, override)
    assert result["nested"]["x"] == 99
    assert result["nested"]["y"] == 2  # preserved from base


def test_deep_merge_does_not_mutate_base():
    base = {"a": {"b": 1}}
    _deep_merge(base, {"a": {"c": 2}})
    assert "c" not in base["a"]


def test_deep_merge_non_dict_override():
    base = {"a": {"nested": 1}}
    result = _deep_merge(base, {"a": "string"})
    assert result["a"] == "string"


# ── _coerce ───────────────────────────────────────────────────────────────────

def test_coerce_string_api_id_to_int():
    assert _coerce("api_id", "12345") == 12345


def test_coerce_string_true_to_bool():
    assert _coerce("auto_read", "true") is True
    assert _coerce("auto_read", "1") is True
    assert _coerce("auto_read", "yes") is True


def test_coerce_string_false_to_bool():
    assert _coerce("auto_read", "false") is False
    assert _coerce("auto_read", "0") is False


def test_coerce_bad_api_id_returns_default():
    result = _coerce("api_id", "not_a_number")
    assert result == DEFAULTS["api_id"]  # 0


def test_coerce_unknown_key_passthrough():
    assert _coerce("unknown_key", "anything") == "anything"


# ── _migrate ──────────────────────────────────────────────────────────────────

def test_migrate_v1_adds_keybinds():
    old = {"api_id": 1, "api_hash": "abc", "schema_version": 1}
    result = _migrate(old)
    assert isinstance(result.get("keybinds"), dict)
    assert result["schema_version"] == 2


def test_migrate_v1_normalises_automations():
    old = {
        "automations": ["keyword"],  # old string format
        "schema_version": 1,
    }
    result = _migrate(old)
    assert isinstance(result["automations"][0], dict)
    assert result["automations"][0]["trigger"] == "keyword"


def test_migrate_already_v2_is_noop():
    data = {"schema_version": 2, "api_id": 42}
    result = _migrate(data)
    assert result["api_id"] == 42
    assert result["schema_version"] == 2


# ── _validate ─────────────────────────────────────────────────────────────────

def test_validate_clamps_invalid_theme():
    data = {**DEFAULTS, "theme": "cyberpunk"}
    result = _validate(data)
    assert result["theme"] == "dark"


def test_validate_fills_missing_keybind_keys():
    data = {**DEFAULTS, "keybinds": {"quit": "x"}}
    result = _validate(data)
    # Should have filled in all other default keybinds
    assert "help" in result["keybinds"]
    assert result["keybinds"]["quit"] == "x"


def test_validate_negative_api_id_clamped():
    data = {**DEFAULTS, "api_id": -5}
    result = _validate(data)
    assert result["api_id"] == 0


# ── Config class ──────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_cfg(tmp_path):
    """Config instance backed by a temp directory."""
    return Config(config_dir=tmp_path)


def test_config_defaults_on_fresh_install(tmp_cfg):
    assert tmp_cfg.get("theme") == "dark"
    assert tmp_cfg.get("msg_limit") == 50
    assert tmp_cfg.is_configured is False


def test_config_set_and_get(tmp_cfg):
    tmp_cfg.set("msg_limit", 100)
    assert tmp_cfg.get("msg_limit") == 100


def test_config_persists_to_disk(tmp_path):
    cfg1 = Config(config_dir=tmp_path)
    cfg1.set("theme", "gruvbox")

    cfg2 = Config(config_dir=tmp_path)
    assert cfg2.get("theme") == "gruvbox"


def test_config_session_name_override(tmp_path):
    cfg = Config(config_dir=tmp_path, session_name="work")
    assert cfg.get("session_name") == "work"


def test_config_is_configured_false_when_no_credentials(tmp_cfg):
    assert tmp_cfg.is_configured is False


def test_config_is_configured_true_with_credentials(tmp_cfg):
    tmp_cfg.set("api_id", 12345)
    tmp_cfg.set("api_hash", "abc123")
    assert tmp_cfg.is_configured is True


@pytest.mark.skipif(sys.platform == "win32", reason="File permissions are not enforced on Windows")
def test_config_file_permissions(tmp_path):
    cfg = Config(config_dir=tmp_path)
    cfg_file = tmp_path / "config.json"
    mode = stat.S_IMODE(os.stat(cfg_file).st_mode)
    assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


def test_config_reset(tmp_cfg):
    tmp_cfg.set("theme", "gruvbox")
    tmp_cfg.set("msg_limit", 200)
    tmp_cfg.reset()
    assert tmp_cfg.get("theme") == "dark"
    assert tmp_cfg.get("msg_limit") == 50


def test_config_handles_corrupt_json(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{ not valid json }")
    cfg = Config(config_dir=tmp_path)
    # Should fall back to defaults without raising
    assert cfg.get("theme") == "dark"


def test_config_atomic_write(tmp_path):
    """Ensures .tmp file is used and then renamed."""
    cfg = Config(config_dir=tmp_path)
    cfg.set("theme", "tokyo")
    # No .tmp file should remain after write
    tmp_file = tmp_path / "config.tmp"
    assert not tmp_file.exists()
    assert (tmp_path / "config.json").exists()


def test_config_dump_hides_api_hash(tmp_path):
    cfg = Config(config_dir=tmp_path)
    cfg.set("api_id", 1)
    cfg.set("api_hash", "supersecret")
    dumped = json.loads(cfg.dump())
    assert "api_hash" not in dumped


def test_config_keybinds_deep_merge(tmp_path):
    """User keybinds should be merged with defaults, not replaced."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "schema_version": 2,
        "api_id": 1,
        "api_hash": "x",
        "keybinds": {"quit": "Q"}  # only override quit
    }))
    cfg = Config(config_dir=tmp_path)
    assert cfg.keybinds["quit"] == "Q"
    assert "help" in cfg.keybinds  # default preserved
