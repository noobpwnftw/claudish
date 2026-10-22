"""Generate the small code-drawn cd icon; no imaging dependencies."""
import struct
import zlib
from pathlib import Path

glyphs = ["00000000000", "01110000100", "10000000100", "10000011100",
          "10000100100", "10000100100", "01110011100"]
rows = []
for y in range(32):
    row = bytearray()
    for x in range(32):
        gx, gy = (x - 5) // 2, (y - 9) // 2
        on = 0 <= gx < 11 and 0 <= gy < 7 and glyphs[gy][gx] == "1"
        row.extend((94, 234, 212, 255) if on else (24, 28, 39, 255))
    rows.append(b"\x00" + row)

def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))
ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(png), 22) + png
target = Path(__file__).resolve().parents[1] / "platforms/windows/claudish/icon.ico"
target.write_bytes(ico)
