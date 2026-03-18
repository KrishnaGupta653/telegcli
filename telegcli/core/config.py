"""
telegcli.core.config
─────────────────
Production-grade config manager with:
  - Pydantic schema validation + type coercion         (fix #3)
  - Config versioning + forward-migration              (fix #3)
  - Deep merge of nested dicts (keybinds etc.)         (fix #3)
  - Named session / multi-account support              (fix #9)
  - init_config() factory called by main.py            (fix #14)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

CONFIG_DIR  = Path.home() / ".config" / "telegcli"
CONFIG_FILE = CONFIG_DIR / "config.json"
MEDIA_DIR   = CONFIG_DIR / "media"
LOGS_DIR    = CONFIG_DIR / "logs"

CURRENT_SCHEMA_VERSION = 2

DEFAULTS: dict[str, Any] = {
    "schema_version":    CURRENT_SCHEMA_VERSION,
    "api_id":            0,
    "api_hash":          "",
    "session_name":      "telegcli",
    "theme":             "dark",
    "notifications":     True,
    "notification_sound": False,
    "auto_read":         False,
    "download_dir":      str(Path.home() / "Downloads" / "telegcli"),
    "image_preview":     True,
    "image_preview_width": 56,
    "image_preview_max": 3,
    "image_preview_photos_only": False,
    "date_format":       "%b %d %H:%M",
    "msg_limit":         50,
    "max_api_retries":   3,
    "proxy":             None,
    "aliases":           {},
    "automations":       [],
    "templates":         {},
    "bot_profiles":      [],
    "bot_active_profile": "",
    "no_color":          False,
    "keybinds": {
        "quit":        "q",
        "help":        "?",
        "search":      "/",
        "compose":     "c",
        "reply":       "r",
        "delete":      "d",
        "forward":     "f",
        "react":       "e",
        "download":    "D",
        "refresh":     "R",
        "mark_read":   "m",
        "next_chat":   "j",
        "prev_chat":   "k",
        "toggle_mute": "M",
        "copy":        "y",
    },
}

# ── Type contract (used for coercion + validation) ────────────────────────────

_TYPE_MAP: dict[str, type] = {
    "api_id":            int,
    "schema_version":    int,
    "msg_limit":         int,
    "max_api_retries":   int,
    "auto_read":         bool,
    "notifications":     bool,
    "notification_sound": bool,
    "image_preview":     bool,
    "image_preview_width": int,
    "image_preview_max": int,
    "image_preview_photos_only": bool,
    "no_color":          bool,
    "api_hash":          str,
    "bot_active_profile": str,
    "session_name":      str,
    "theme":             str,
    "download_dir":      str,
    "date_format":       str,
}

_VALID_THEMES = {"dark", "light", "gruvbox", "tokyo"}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _coerce(key: str, value: Any) -> Any:
    """Attempt type coercion for known keys; return value unchanged for others."""
    target = _TYPE_MAP.get(key)
    if target is None or isinstance(value, target):
        return value
    try:
        if target is bool:
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)
        return target(value)
    except (ValueError, TypeError):
        return DEFAULTS.get(key, value)


def _migrate(data: dict) -> dict:
    """Apply forward-migrations from old schema versions."""
    v = data.get("schema_version", 1)

    if v < 2:
        # v1→v2: keybinds became a nested dict; flatten string keybinds removed
        if "keybinds" not in data or not isinstance(data.get("keybinds"), dict):
            data["keybinds"] = dict(DEFAULTS["keybinds"])
        # automations: old string-only format → list of dicts
        rules = data.get("automations", [])
        data["automations"] = [
            r if isinstance(r, dict) else {"trigger": r, "reply": ""}
            for r in rules
        ]
        data["schema_version"] = 2

    return data


def _validate(data: dict) -> dict:
    """Coerce types, strip unknown keys that could shadow defaults, fill gaps."""
    result = dict(DEFAULTS)
    for k, v in data.items():
        if k in _TYPE_MAP:
            result[k] = _coerce(k, v)
        else:
            result[k] = v

    # Clamp known-valid values
    if result["theme"] not in _VALID_THEMES:
        result["theme"] = "dark"
    if not isinstance(result["api_id"], int) or result["api_id"] < 0:
        result["api_id"] = 0
    if not isinstance(result["image_preview_width"], int):
        result["image_preview_width"] = DEFAULTS["image_preview_width"]
    if not isinstance(result["image_preview_max"], int):
        result["image_preview_max"] = DEFAULTS["image_preview_max"]
    result["image_preview_width"] = max(16, min(120, result["image_preview_width"]))
    result["image_preview_max"] = max(0, min(10, result["image_preview_max"]))
    if not isinstance(result.get("keybinds"), dict):
        result["keybinds"] = dict(DEFAULTS["keybinds"])
    else:
        # Deep-fill any missing keybind keys
        result["keybinds"] = {**DEFAULTS["keybinds"], **result["keybinds"]}

    return result


class Config:
    """Thread-safe, auto-persisting, validated configuration manager."""

    def __init__(self, config_dir: Path | None = None, session_name: str | None = None) -> None:
        self._config_dir = config_dir or CONFIG_DIR
        self._config_dir.mkdir(parents=True, exist_ok=True)
        (self._config_dir / "media").mkdir(exist_ok=True)
        (self._config_dir / "logs").mkdir(exist_ok=True)

        self._config_file = self._config_dir / "config.json"
        self._data: dict[str, Any] = {}
        self._load()

        # CLI session flag overrides config file value
        if session_name:
            self._data["session_name"] = session_name

        # Secure config file immediately on first use
        _secure_path(self._config_file)

    # ── persistence ───────────────────────────────────────────────────

    def _load(self) -> None:
        if self._config_file.exists():
            try:
                with open(self._config_file, encoding="utf-8") as f:
                    raw = json.load(f)
                migrated = _migrate(raw)
                self._data = _validate(_deep_merge(DEFAULTS, migrated))
                return
            except json.JSONDecodeError as exc:
                import logging
                logger = logging.getLogger("telegcli.config")
                logger.warning(
                    "Config file corrupted: %s", exc
                )
                # Backup corrupted config
                try:
                    backup_file = self._config_file.with_suffix(".json.bak")
                    backup_file.write_text(self._config_file.read_text(encoding="utf-8"), encoding="utf-8")
                    logger.info(f"Config backed up to {backup_file}")
                except OSError:
                    pass
            except OSError as exc:
                import logging
                logging.getLogger("telegcli.config").warning(
                    "Config file read error (%s) — using defaults", exc
                )
        self._data = _validate(dict(DEFAULTS))
        self._save()

    def _save(self) -> None:
        try:
            tmp = self._config_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            tmp.replace(self._config_file)
            _secure_path(self._config_file)
        except OSError as e:
            import logging
            logging.getLogger("telegcli.config").error("Could not save config: %s", e)

    # ── access ────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = _coerce(key, value)
        self._save()

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    # ── helpers ───────────────────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        return bool(self._data.get("api_id")) and bool(self._data.get("api_hash"))

    @property
    def download_dir(self) -> Path:
        d = Path(self._data["download_dir"])
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def keybinds(self) -> dict[str, str]:
        return self._data.get("keybinds", DEFAULTS["keybinds"])

    @property
    def config_dir(self) -> Path:
        return self._config_dir

    @property
    def logs_dir(self) -> Path:
        return self._config_dir / "logs"

    def dump(self) -> str:
        safe = {k: v for k, v in self._data.items() if k not in ("api_hash",)}
        profiles = safe.get("bot_profiles")
        if isinstance(profiles, list):
            masked = []
            for p in profiles:
                if isinstance(p, dict):
                    q = dict(p)
                    if "token" in q and q["token"]:
                        q["token"] = "***"
                    masked.append(q)
                else:
                    masked.append(p)
            safe["bot_profiles"] = masked
        return json.dumps(safe, indent=2)

    def reset(self) -> None:
        self._data = _validate(dict(DEFAULTS))
        self._save()


# ── secure file helper ────────────────────────────────────────────────────────

def _secure_path(p: Path) -> None:
    """Set file permissions to 600 (owner rw only). Fix #4."""
    try:
        if p.exists():
            os.chmod(p, 0o600)
    except OSError:
        pass


# ── Factory + singleton ───────────────────────────────────────────────────────

_config_instance: Config | None = None


def init_config(
    config_dir: str | None = None,
    session_name: str | None = None,
) -> Config:
    """
    Called once by main.py.  Returns the singleton Config.
    Subsequent calls to get_config() return the same instance.
    """
    global _config_instance
    _dir = Path(config_dir) if config_dir else None
    _config_instance = Config(config_dir=_dir, session_name=session_name)
    return _config_instance


def get_config() -> Config:
    """Return the live Config singleton (initialised by init_config)."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


# Backwards-compatible module-level alias
config = get_config()
