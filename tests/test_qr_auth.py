"""Tests for QR authentication flow in telegcli.core.client."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegcli.core.client import teleclient


@pytest.mark.asyncio
async def test_authorize_with_qr_continues_when_show_qr_fails():
    tc = teleclient()

    qr_login = MagicMock()
    qr_login.url = "tg://login?token=test"
    qr_login.wait = AsyncMock(return_value=None)

    tc._client = MagicMock()
    tc._client.qr_login = AsyncMock(return_value=qr_login)

    show_error = AsyncMock()
    show_qr = AsyncMock(side_effect=RuntimeError("render failed"))

    ok = await tc._authorize_with_qr({
        "show_error": show_error,
        "show_qr": show_qr,
        "get_2fa": AsyncMock(return_value="secret"),
    })

    assert ok is True
    show_qr.assert_awaited_once_with("tg://login?token=test")
    qr_login.wait.assert_awaited_once_with(timeout=120)
    assert show_error.await_count == 2


@pytest.mark.asyncio
async def test_ensure_authorized_qr_timeout_falls_back_to_phone():
    tc = teleclient()
    tc._client = MagicMock()
    tc._client.is_user_authorized = AsyncMock(return_value=False)
    tc._client.get_me = AsyncMock(return_value=MagicMock(first_name="Test", id=1))

    tc._authorize_with_qr = AsyncMock(return_value=False)
    tc._authorize_with_phone = AsyncMock(return_value=True)

    show_error = AsyncMock()
    choose_login_method = AsyncMock(return_value="qr")

    ok = await tc.ensure_authorized({
        "choose_login_method": choose_login_method,
        "show_error": show_error,
        "get_phone": AsyncMock(return_value="+10000000000"),
        "get_code": AsyncMock(return_value="12345"),
        "get_2fa": AsyncMock(return_value="secret"),
        "show_qr": AsyncMock(),
    })

    assert ok is True
    tc._authorize_with_qr.assert_awaited_once()
    tc._authorize_with_phone.assert_awaited_once()
    show_error.assert_any_await("QR login failed or timed out. Falling back to OTP login.")


@pytest.mark.asyncio
async def test_ensure_authorized_qr_fatal_invalid_api_stops_flow():
    tc = teleclient()
    tc._client = MagicMock()
    tc._client.is_user_authorized = AsyncMock(return_value=False)

    tc._authorize_with_qr = AsyncMock(return_value=None)
    tc._authorize_with_phone = AsyncMock(return_value=True)

    show_error = AsyncMock()
    choose_login_method = AsyncMock(return_value="qr")

    ok = await tc.ensure_authorized({
        "choose_login_method": choose_login_method,
        "show_error": show_error,
        "get_phone": AsyncMock(return_value="+10000000000"),
        "get_code": AsyncMock(return_value="12345"),
        "get_2fa": AsyncMock(return_value="secret"),
        "show_qr": AsyncMock(),
    })

    assert ok is False
    tc._authorize_with_qr.assert_awaited_once()
    tc._authorize_with_phone.assert_not_awaited()
