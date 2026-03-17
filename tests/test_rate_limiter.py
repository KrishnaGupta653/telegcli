"""
Tests for telegcli.core.rate_limiter

Covers: FloodWaitError retry, ServerError retry, AuthKeyError passthrough,
        BadRequestError no-retry, max retry exhaustion.
"""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from telethon.errors import (
    FloodWaitError,
    ServerError,
    AuthKeyError,
    BadRequestError,
)

from telegcli.core.rate_limiter import rate_limited, MAX_RETRIES


# ── helpers ───────────────────────────────────────────────────────────────────

def make_flood_error(seconds: int) -> FloodWaitError:
    e = FloodWaitError.__new__(FloodWaitError)
    e.seconds = seconds
    e.message = f"A wait of {seconds} seconds is required"
    return e


def make_server_error() -> ServerError:
    e = ServerError.__new__(ServerError)
    e.message = "Internal server error"
    return e


def make_auth_error() -> AuthKeyError:
    e = AuthKeyError.__new__(AuthKeyError)
    e.message = "Auth key unregistered"
    return e


def make_bad_request() -> BadRequestError:
    e = BadRequestError.__new__(BadRequestError)
    e.message = "Bad request"
    return e


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limited_passthrough_on_success():
    call_count = 0

    @rate_limited
    async def my_func():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await my_func()
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_rate_limited_retries_on_flood_wait():
    call_count = 0

    @rate_limited
    async def my_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise make_flood_error(0)
        return "ok"

    with patch("telegcli.core.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with patch("telegcli.core.rate_limiter.print_warning"):
            result = await my_func()

    assert result == "ok"
    assert call_count == 2
    mock_sleep.assert_called_once_with(1)  # 0 seconds + 1 buffer


@pytest.mark.asyncio
async def test_rate_limited_raises_after_max_retries():
    @rate_limited
    async def always_flood():
        raise make_flood_error(0)

    with patch("telegcli.core.rate_limiter.asyncio.sleep", new_callable=AsyncMock):
        with patch("telegcli.core.rate_limiter.print_warning"):
            with pytest.raises(FloodWaitError):
                await always_flood()


@pytest.mark.asyncio
async def test_rate_limited_retries_server_error():
    call_count = 0

    @rate_limited
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise make_server_error()
        return "recovered"

    with patch("telegcli.core.rate_limiter.asyncio.sleep", new_callable=AsyncMock):
        result = await flaky()

    assert result == "recovered"
    assert call_count == 2


@pytest.mark.asyncio
async def test_rate_limited_does_not_retry_auth_error():
    call_count = 0

    @rate_limited
    async def auth_fail():
        nonlocal call_count
        call_count += 1
        raise make_auth_error()

    with pytest.raises(AuthKeyError):
        await auth_fail()

    assert call_count == 1  # no retry


@pytest.mark.asyncio
async def test_rate_limited_does_not_retry_bad_request():
    call_count = 0

    @rate_limited
    async def bad_req():
        nonlocal call_count
        call_count += 1
        raise make_bad_request()

    with pytest.raises(BadRequestError):
        await bad_req()

    assert call_count == 1  # no retry


@pytest.mark.asyncio
async def test_rate_limited_preserves_function_name():
    @rate_limited
    async def my_named_func():
        return True

    assert my_named_func.__name__ == "my_named_func"


@pytest.mark.asyncio
async def test_rate_limited_flood_wait_respects_seconds():
    waited = []

    @rate_limited
    async def one_flood():
        if not waited:
            raise make_flood_error(30)
        return "ok"

    async def mock_sleep(s):
        waited.append(s)

    with patch("telegcli.core.rate_limiter.asyncio.sleep", side_effect=mock_sleep):
        with patch("telegcli.core.rate_limiter.print_warning"):
            await one_flood()

    assert waited[0] == 31  # 30 + 1 buffer

