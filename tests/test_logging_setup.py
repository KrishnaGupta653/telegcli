"""
Tests for telegcli.core.logging_setup
"""

import logging
import os
from pathlib import Path

import pytest


def test_setup_logging_creates_log_file(tmp_path):
    # Reset _CONFIGURED so we can test fresh
    import telegcli.core.logging_setup as ls
    ls._CONFIGURED = False

    logs_dir = tmp_path / "logs"
    ls.setup_logging("WARNING", logs_dir=logs_dir)

    assert (logs_dir / "telegcli.log").exists()

    # Reset for other tests
    ls._CONFIGURED = False


def test_setup_logging_is_idempotent(tmp_path):
    import telegcli.core.logging_setup as ls
    ls._CONFIGURED = False

    logs_dir = tmp_path / "logs"
    ls.setup_logging("WARNING", logs_dir=logs_dir)
    handler_count_after_first = len(logging.getLogger().handlers)

    ls.setup_logging("WARNING", logs_dir=logs_dir)  # second call
    handler_count_after_second = len(logging.getLogger().handlers)

    assert handler_count_after_first == handler_count_after_second

    ls._CONFIGURED = False


def test_setup_logging_silences_telethon(tmp_path):
    import telegcli.core.logging_setup as ls
    ls._CONFIGURED = False

    logs_dir = tmp_path / "logs"
    ls.setup_logging("DEBUG", logs_dir=logs_dir)

    assert logging.getLogger("telethon").level == logging.WARNING

    ls._CONFIGURED = False
