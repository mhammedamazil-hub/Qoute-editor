"""Screen capture + annotation helpers for AI vision batches."""
from __future__ import annotations

import base64
import io
import os


def capture(path=None):
    """Screenshot bytes + path. Returns (path, png_bytes) or ('', b'')."""
    from ..system import display as _display
    p = _display.screenshot(path)
    if not p:
        return "", b""
    try:
        with open(p, "rb") as fh:
            return p, fh.read()
    except OSError:
        return p, b""


def downscale_for_ai(png_bytes, max_width=1280):
    """Shrink screenshot so cloud vision calls stay fast & cheap."""
    if not png_bytes:
        return b""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        if img.width > max_width:
            h = int(img.height * max_width / img.width)
            img = img.resize((max_width, h))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=72)
        return buf.getvalue()
    except Exception:
        return png_bytes


def to_data_url(image_bytes, mime="image/jpeg"):
    if not image_bytes:
        return ""
    return "data:%s;base64,%s" % (
        mime, base64.b64encode(image_bytes).decode("ascii"))
