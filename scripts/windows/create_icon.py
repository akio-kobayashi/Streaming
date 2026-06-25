from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def make_png(size: int) -> bytes:
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            nx = x / max(1, size - 1)
            ny = y / max(1, size - 1)
            r, g, b, a = 5, 7, 11, 255

            # Rounded-square background.
            margin = size * 0.04
            radius = size * 0.18
            dx = max(margin - x, 0, x - (size - margin))
            dy = max(margin - y, 0, y - (size - margin))
            if dx * dx + dy * dy > radius * radius:
                a = 0

            # Caption panel.
            if 0.18 < nx < 0.82 and 0.2 < ny < 0.38:
                r, g, b = 17, 24, 39
            if 0.24 < nx < 0.54 and 0.26 < ny < 0.29:
                r, g, b = 255, 255, 255
            if 0.24 < nx < 0.74 and 0.32 < ny < 0.35:
                r, g, b = 208, 208, 208

            # Spectrogram-like waves.
            wave = 0.65 + 0.16 * (
                ((x // max(1, size // 24)) % 2) * 2 - 1
            ) * abs(0.5 - nx)
            if 0.18 < nx < 0.84 and abs(ny - wave) < 0.045:
                r, g, b = 255, 173, 59
            elif 0.16 < nx < 0.86 and abs(ny - wave) < 0.085:
                r, g, b = 255, 63, 164

            # Subtitle baseline.
            if 0.2 < nx < 0.8 and 0.82 < ny < 0.87:
                r, g, b = 248, 250, 252
            if 0.28 < nx < 0.64 and 0.82 < ny < 0.87:
                r, g, b = 96, 165, 250

            row.extend([r, g, b, a])
        rows.append(bytes(row))

    raw = b"".join(rows)
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(raw, 9))
    png += png_chunk(b"IEND", b"")
    return png


def write_ico(path: Path, sizes: list[int]) -> None:
    images = [make_png(size) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = bytearray()
    body = bytearray()

    for size, image in zip(sizes, images):
        width = 0 if size >= 256 else size
        height = 0 if size >= 256 else size
        entries.extend(struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, len(image), offset))
        body.extend(image)
        offset += len(image)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Windows ICO for Streaming ASR Client")
    parser.add_argument("output", nargs="?", default="assets/app-icon.ico")
    args = parser.parse_args()
    write_ico(Path(args.output), [16, 32, 48, 256])


if __name__ == "__main__":
    main()
