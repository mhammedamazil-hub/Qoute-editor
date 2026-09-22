#!/usr/bin/env python3
"""Generate the JARVISOS default wallpaper (1920×1080 PNG, stdlib only).

Dark navy radial gradient + faint circuit grid + cyan horizon glow.
Output: filesystem/usr/share/backgrounds/jarvis-default.png
"""
import math
import os
import struct
import zlib

W, H = 1920, 1080


def pixel(x, y):
    # radial falloff from center-top glow point
    dx, dy = (x - W * 0.5) / W, (y - H * 0.42) / H
    dist = math.sqrt(dx * dx + dy * dy)
    glow = max(0.0, 1.0 - dist * 1.9) ** 2
    # horizon band glow near bottom third
    band = max(0.0, 1.0 - abs(y - H * 0.72) / (H * 0.10)) ** 3
    # faint grid
    grid = 1.0 if (x % 96 < 2 or y % 96 < 2) else 0.0
    r = 4 + glow * 22 + band * 8 + grid * 5
    g = 14 + glow * 90 + band * 60 + grid * 12
    b = 28 + glow * 130 + band * 90 + grid * 18
    return int(min(255, r)), int(min(255, g)), int(min(255, b))


def main():
    rows = bytearray()
    for y in range(H):
        rows.append(0)  # filter byte: none
        for x in range(W):
            rows += bytes(pixel(x, y))
        if y % 270 == 0:
            print("  row %d/%d" % (y, H), flush=True)

    def chunk(ctype, data):
        out = struct.pack(">I", len(data)) + ctype + data
        return out + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
           + chunk(b"IEND", b""))
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                        "filesystem", "usr", "share", "backgrounds",
                        "jarvis-default.png")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(png)
    print("wrote %s (%d KB)" % (dest, len(png) // 1024))


if __name__ == "__main__":
    main()
