"""Generate the small code-drawn icons: cd (the input method), and C, I, R (its modes: the Windows
input indicator, and the macOS menu bar as templates). No imaging dependencies."""
import struct
import zlib
from pathlib import Path

GLYPHS = {
    "icon": ["00000000000", "01110000100", "10000000100", "10000011100",
             "10000100100", "10000100100", "01110011100"],
    "mode-continue": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "mode-instruct": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "mode-rewrite": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
}


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png(glyph, on=(94, 234, 212, 255), off=(24, 28, 39, 255)):
    """A 32x32 PNG with the glyph centered, two pixels per dot."""
    width, height = len(glyph[0]), len(glyph)
    left, top = (32 - 2 * width) // 2, (32 - 2 * height) // 2
    dot, blank = bytes(on), bytes(off)
    rows = []
    for y in range(32):
        row = bytearray()
        for x in range(32):
            gx, gy = (x - left) // 2, (y - top) // 2
            lit = 0 <= gx < width and 0 <= gy < height and x >= left and y >= top and glyph[gy][gx] == "1"
            row.extend(dot if lit else blank)
        rows.append(b"\x00" + row)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def ico(glyph):
    image = png(glyph)
    return struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(image), 22) + image


directory = Path(__file__).resolve().parents[1] / "platforms/windows/claudish"
for name, glyph in GLYPHS.items():
    (directory / (name + ".ico")).write_bytes(ico(glyph))
# macOS menu-bar icons: templates (black on transparent; the system tints them).
macos = Path(__file__).resolve().parents[1] / "platforms/macos"
for name, glyph in GLYPHS.items():
    if name.startswith("mode-"):
        (macos / (name + ".png")).write_bytes(png(glyph, on=(0, 0, 0, 255), off=(0, 0, 0, 0)))
