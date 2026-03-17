"""
telegcli.core.logging_setup
                            
Configures structured, rotating file logging + optional console output.
Call setup_logging() once at startup before any other import.

Fix #2: structured logging with rotation to ~/.config/telegcli/logs/telegcli.log
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path


_CONFIGURED = False


def setup_logging(level_name: str = "WARNING", logs_dir: Path | None = None) -> None:
    """
    Configure root logger with:
    - Rotating file handler → logs_dir/telegcli.log  (always at DEBUG level)
      - Console handler       → stderr               (at requested level, only if DEBUG/INFO)

    Safe to call multiple times; only configures once.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    if logs_dir is None:
        from telegcli.core.config import CONFIG_DIR
        logs_dir = CONFIG_DIR / "logs"

    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "telegcli.log"

    level = getattr(logging, level_name.upper(), logging.WARNING)

    fmt = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler — always DEBUG so nothing is lost
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    # Console handler only when user explicitly requests verbose output
    if level <= logging.INFO:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(fmt)
        root.addHandler(console_handler)

    # Silence overly chatty third-party loggers
    for noisy in ("telethon", "asyncio", "urllib3", "aiohttp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("telegcli").setLevel(level)
    logging.getLogger("telegcli").info("Logging initialised — file: %s", log_file)
