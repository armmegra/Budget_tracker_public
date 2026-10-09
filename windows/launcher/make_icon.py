"""Draws the application icon."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "budget.ico"

SIZES = (16, 24, 32, 48, 64, 128, 256)
GREEN = (0x3F, 0x9D, 0x5A)
WHITE = (0xFF, 0xFF, 0xFF)
SUPER = 4


def _inside_rounded_square(x: float, y: float, n: float, radius: float) -> bool:
    if x < 0 or y < 0 or x >= n or y >= n:
        return False
    cx = radius if x < radius else (n - radius if x > n - radius else x)
    cy = radius if y < radius else (n - radius if y > n - radius else y)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def _bars(n: float) -> list[tuple[float, float, float, float]]:
    width, gap = n * 0.17, n * 0.075
    total = 3 * width + 2 * gap
    left0 = (n - total) / 2
    bottom = n * 0.78
    heights = (n * 0.28, n * 0.42, n * 0.56)
    bars = []
    for i, h in enumerate(heights):
        left = left0 + i * (width + gap)
        bars.append((left, bottom - h, left + width, bottom))
    return bars


def _pixels(n: int) -> bytes:
    radius = n * 0.22
    bars = _bars(n)
    step = 1.0 / SUPER
    rows = bytearray()
    for py in range(n):
        rows.append(0)
        for px in range(n):
            ground = 0
            bar = 0
            for sy in range(SUPER):
                for sx in range(SUPER):
                    x = px + (sx + 0.5) * step
                    y = py + (sy + 0.5) * step
                    if not _inside_rounded_square(x, y, n, radius):
                        continue
                    ground += 1
                    for left, top, right, bottom in bars:
                        if left <= x < right and top <= y < bottom:
                            bar += 1
                            break
            samples = SUPER * SUPER
            alpha = round(255 * ground / samples)
            if ground == 0:
                rows.extend((0, 0, 0, 0))
                continue
            t = bar / ground
            r = round(GREEN[0] + (WHITE[0] - GREEN[0]) * t)
            g = round(GREEN[1] + (WHITE[1] - GREEN[1]) * t)
            b = round(GREEN[2] + (WHITE[2] - GREEN[2]) * t)
            rows.extend((r, g, b, alpha))
    return bytes(rows)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def png(n: int) -> bytes:
    header = struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(_pixels(n), 9))
        + _chunk(b"IEND", b"")
    )


def ico(sizes: tuple[int, ...] = SIZES) -> bytes:
    images = [png(n) for n in sizes]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = len(head) + 16 * len(images)
    entries = b""
    for n, blob in zip(sizes, images):
        side = 0 if n >= 256 else n
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    return head + entries + b"".join(images)


def main() -> int:
    OUT.write_bytes(ico())
    print(f"  icon: {OUT.relative_to(HERE.parent)}  ({OUT.stat().st_size} bytes, "
          f"{len(SIZES)} sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
