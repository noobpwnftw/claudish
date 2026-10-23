"""Generate the small code-drawn icons: cd (the input method), and C, AI (its modes, continue and compose, for the
Windows input indicator). No imaging dependencies."""
import struct
import zlib
from pathlib import Path

GLYPHS = {
    "icon": ["00000000000", "01110000100", "10000000100", "10000011100",
             "10000100100", "10000100100", "01110011100"],
    "mode-continue": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "mode-compose": ["01110011100", "10001001000", "10001001000", "11111001000",
                     "10001001000", "10001001000", "10001011100"],
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
# macOS: the input source's menu-bar icon, a template (black on transparent; the system tints it).
# platforms/macos/build.py converts it to TIFF with sips, which macOS loads for input sources.
(Path(__file__).resolve().parents[1] / "platforms/macos/cd.png").write_bytes(
    png(GLYPHS["icon"], on=(0, 0, 0, 255), off=(0, 0, 0, 0)))
