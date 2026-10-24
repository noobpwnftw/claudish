"""A picture of the focused window, taken only when an instruction asks for it (F8 in instruct mode).

The service runs as the user on the same desktop, so it captures the window the input method is
typing into. The PNG goes to the configured backend with that one request. Linux X11 uses ImageMagick's `import`; Windows uses PrintWindow; elsewhere (Wayland, macOS)
a profile sets `look_command`, a program that writes a PNG of the focused window to stdout.
"""
import os
import platform
import shutil
import struct
import subprocess
import zlib

MAX_SIDE = 1568  # larger pictures cost more and do not help a vision model read a window


class CaptureError(RuntimeError):
    pass


def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise CaptureError("the capture is not a PNG")
    return struct.unpack(">II", data[16:24])


def encode_png(width, height, rows):
    """rows: `height` bytes objects of width*3 RGB bytes. Standard library only."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def run(command, timeout):
    try:
        done = subprocess.run(command, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CaptureError("window capture failed: %s" % exc)
    if done.returncode != 0 or not done.stdout:
        raise CaptureError("window capture failed: %s" % done.stderr.decode(errors="replace").strip()[-200:])
    return done.stdout


def capture_x11(timeout):
    if not (shutil.which("xprop") and shutil.which("import")):
        raise CaptureError("window pictures on X11 need xprop and ImageMagick: sudo apt install x11-utils imagemagick")
    # Window managers publish the active window; without one (a bare X server), ask X for the focus.
    active = run(["xprop", "-root", "_NET_ACTIVE_WINDOW"], timeout).decode().rsplit(" ", 1)[-1].strip()
    if not (active.startswith("0x") and int(active, 16)) and shutil.which("xdotool"):
        active = run(["xdotool", "getwindowfocus"], timeout).decode().strip()
    if not active or active in ("0", "0x0") or not (active.startswith("0x") or active.isdigit()):
        raise CaptureError("no focused window to capture")
    return run(["import", "-silent", "-window", active, "-resize", "%dx%d>" % (MAX_SIDE, MAX_SIDE), "png:-"], timeout)


def capture_windows():
    import ctypes
    from ctypes import wintypes
    user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
    H, HWND, UINT = wintypes.HANDLE, wintypes.HWND, wintypes.UINT
    for function, argtypes, restype in [
            (user32.GetForegroundWindow, [], HWND), (user32.GetWindowRect, [HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            (user32.GetDC, [HWND], H), (user32.ReleaseDC, [HWND, H], ctypes.c_int),
            (user32.PrintWindow, [HWND, H, UINT], wintypes.BOOL),
            (gdi32.CreateCompatibleDC, [H], H), (gdi32.CreateCompatibleBitmap, [H, ctypes.c_int, ctypes.c_int], H),
            (gdi32.SelectObject, [H, H], H), (gdi32.DeleteObject, [H], wintypes.BOOL), (gdi32.DeleteDC, [H], wintypes.BOOL),
            (gdi32.GetDIBits, [H, H, UINT, UINT, ctypes.c_void_p, ctypes.c_void_p, UINT], ctypes.c_int)]:
        function.argtypes, function.restype = argtypes, restype

    class Header(ctypes.Structure):  # BITMAPINFOHEADER
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    hwnd, rect = user32.GetForegroundWindow(), wintypes.RECT()
    if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise CaptureError("no focused window to capture")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise CaptureError("the focused window has no area")
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    try:
        gdi32.SelectObject(memory, bitmap)
        # PW_RENDERFULLCONTENT (2) includes DirectComposition content, such as browsers.
        if not user32.PrintWindow(hwnd, memory, 2):
            raise CaptureError("PrintWindow failed")
        header = Header(biSize=ctypes.sizeof(Header), biWidth=width, biHeight=-height, biPlanes=1, biBitCount=32)
        pixels = ctypes.create_string_buffer(width * height * 4)
        if gdi32.GetDIBits(memory, bitmap, 0, height, pixels, ctypes.byref(header), 0) != height:
            raise CaptureError("could not read the window's pixels")
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)
    return bgra_to_png(pixels.raw, width, height)


def bgra_to_png(data, width, height):
    """Top-down BGRA to RGB PNG, shrunk by a whole-number step to fit MAX_SIDE."""
    step = max(1, -(-max(width, height) // MAX_SIDE))
    rows = []
    for y in range(0, height, step):
        line = data[y * width * 4:(y + 1) * width * 4]
        pixels = line[::4 * step], line[1::4 * step], line[2::4 * step]  # B, G, R of every step-th pixel
        rgb = bytearray(len(pixels[0]) * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = pixels[2], pixels[1], pixels[0]
        rows.append(bytes(rgb))
    return encode_png(len(rows[0]) // 3, len(rows), rows)


def capture(command=None, timeout=5):
    """(png bytes, width, height) of the focused window."""
    if command:
        data = run(command, timeout)
    elif platform.system() == "Windows":
        data = capture_windows()
    elif platform.system() == "Linux" and os.environ.get("DISPLAY"):
        data = capture_x11(timeout)
    else:
        raise CaptureError("no built-in window capture here (Wayland, macOS): set the profile's look_command "
                           "to a program that writes a PNG of the focused window to stdout")
    width, height = png_size(data)
    return data, width, height
