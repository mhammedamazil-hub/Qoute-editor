"""Pixel buffer utilities: 8-bit RGB PNG encoder and simple 2D drawing (stdlib only).

Pixels are stored as a flat ``bytearray`` in row-major order, three bytes per pixel (R, G, B).
"""

from __future__ import annotations

import struct
import zlib
from typing import Tuple

Color = Tuple[int, int, int]


def new_buffer(width: int, height: int, fill: Color = (0, 0, 0)) -> bytearray:
    return bytearray(bytes(fill) * (width * height))


def encode_png(width: int, height: int, pixels: bytearray) -> bytes:
    """Encode an RGB buffer as a PNG file (filter type 0 on every row, zlib level 9, no metadata chunks)."""
    if len(pixels) != width * height * 3:
        raise ValueError("pixel buffer size does not match width x height x 3")
    stride = width * 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += pixels[y * stride:(y + 1) * stride]

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit, colour type 2 (RGB)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def set_pixel(buf: bytearray, width: int, height: int, x: int, y: int, color: Color) -> None:
    if 0 <= x < width and 0 <= y < height:
        i = (y * width + x) * 3
        buf[i] = color[0]
        buf[i + 1] = color[1]
        buf[i + 2] = color[2]


def draw_line(buf: bytearray, width: int, height: int, x0: float, y0: float, x1: float, y1: float,
              color: Color, thickness: int = 1) -> None:
    """Bresenham line with a square brush of ``thickness`` pixels. Endpoints may lie outside the image."""
    ix0, iy0, ix1, iy1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    dx, dy = abs(ix1 - ix0), -abs(iy1 - iy0)
    sx = 1 if ix0 < ix1 else -1
    sy = 1 if iy0 < iy1 else -1
    err = dx + dy
    half = thickness // 2
    x, y = ix0, iy0
    while True:
        for oy in range(-half, half + 1):
            for ox in range(-half, half + 1):
                set_pixel(buf, width, height, x + ox, y + oy, color)
        if x == ix1 and y == iy1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


def fill_disc(buf: bytearray, width: int, height: int, cx: float, cy: float, radius: float, color: Color) -> None:
    r = max(0.5, radius)
    x_lo, x_hi = int(cx - r) - 1, int(cx + r) + 1
    y_lo, y_hi = int(cy - r) - 1, int(cy + r) + 1
    r2 = r * r
    for y in range(max(0, y_lo), min(height, y_hi + 1)):
        for x in range(max(0, x_lo), min(width, x_hi + 1)):
            if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r2:
                set_pixel(buf, width, height, x, y, color)
