from unittest.mock import AsyncMock

import pytest

from telegcli.utils.media_preview import (
    image_bytes_to_ascii,
    is_image_message,
    render_message_image_preview,
)


class _Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _sample_png_bytes() -> bytes:
    from PIL import Image
    from io import BytesIO

    img = Image.new("RGB", (24, 24), color=(255, 0, 0))
    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def test_is_image_message_detects_photo():
    msg = _Obj(photo=object(), media=None)
    assert is_image_message(msg) is True


def test_is_image_message_detects_document_mime_image():
    doc = _Obj(mime_type="image/jpeg")
    media = _Obj(document=doc)
    msg = _Obj(photo=None, media=media)
    assert is_image_message(msg) is True


def test_is_image_message_rejects_non_image_document():
    doc = _Obj(mime_type="application/pdf")
    media = _Obj(document=doc)
    msg = _Obj(photo=None, media=media)
    assert is_image_message(msg) is False


def test_image_bytes_to_ascii_returns_text_for_valid_image():
    ascii_art = image_bytes_to_ascii(_sample_png_bytes(), width=24)
    assert ascii_art
    assert "\n" in ascii_art


@pytest.mark.asyncio
async def test_render_message_image_preview_returns_none_for_non_image():
    client = _Obj(download_media=AsyncMock())
    msg = _Obj(photo=None, media=None)
    out = await render_message_image_preview(client, msg)
    assert out is None
    client.download_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_render_message_image_preview_renders_ascii_for_image():
    client = _Obj(download_media=AsyncMock(return_value=_sample_png_bytes()))
    msg = _Obj(photo=object(), media=None)

    out = await render_message_image_preview(client, msg, width=24)
    assert out
    client.download_media.assert_awaited_once()
