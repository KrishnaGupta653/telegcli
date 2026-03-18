"""Helpers for rendering Telegram image media previews in terminal."""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any, Optional


ASCII_RAMP = " .:-=+*#%@"


def is_image_message(msg: Any) -> bool:
    """Return True if a Telegram message likely contains an image."""
    if getattr(msg, "photo", None) is not None:
        return True

    media = getattr(msg, "media", None)
    doc = getattr(media, "document", None)
    mime = (getattr(doc, "mime_type", "") or "").lower() if doc else ""
    return mime.startswith("image/")


def image_bytes_to_ascii(image_data: bytes, width: int = 64) -> Optional[str]:
    """Convert image bytes into an ASCII-art preview for terminal display."""
    if not image_data:
        return None

    from PIL import Image

    with Image.open(BytesIO(image_data)) as img:
        img = img.convert("L")

        # Terminal characters are taller than they are wide; compensate height.
        src_w, src_h = img.size
        if src_w <= 0 or src_h <= 0:
            return None

        width = max(16, min(width, 120))
        ratio = src_h / src_w
        out_h = max(8, int(width * ratio * 0.55))
        img = img.resize((width, out_h))

        pixels = list(img.getdata())
        chars = [ASCII_RAMP[min(len(ASCII_RAMP) - 1, px * len(ASCII_RAMP) // 256)] for px in pixels]

        lines = []
        for i in range(0, len(chars), width):
            lines.append("".join(chars[i:i + width]))
        return "\n".join(lines)


async def render_message_image_preview(client: Any, msg: Any, width: int = 64) -> Optional[str]:
    """Download and render a message image as ASCII preview text."""
    if not is_image_message(msg):
        return None

    try:
        data = await client.download_media(msg, file=bytes)
    except Exception:
        return None

    if not isinstance(data, (bytes, bytearray)):
        return None

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, image_bytes_to_ascii, bytes(data), width)
