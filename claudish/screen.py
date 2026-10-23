"""What a terminal shows, read through the accessibility APIs screen readers use (G35).

A terminal is not a text box: the input method protocols give nothing around the caret, and it
publishes no MCP. Its accessible element does expose the visible screen (prompts, commands,
errors), so an instruction typed at a terminal prompt ("fix") can see what just happened, with
nothing installed in the shell. Read only when an instruction or a rewrite asks (never on
continue's pauses), only for a focused terminal, never logged, and only the last lines.

Linux: AT-SPI (the accessibility bus GNOME and KDE run). Windows: UI Automation through ctypes.
macOS: the AX API through pyobjc; the service's Python needs the Accessibility permission.
Keep importable on PIME's Python 3.6: adapters use `is_terminal` for quiet continue.
"""
import sys
import time

MAX_LINES = 40
MAX_CHARS = 4000
BUDGET_SECONDS = 0.5  # a slow accessibility tree must not hold up the answer

# Terminal programs as the adapters name the focused app: IBus program names (Linux), executables
# (Windows; a classic console window reports its shell), and bundle identifiers (macOS).
TERMINALS = {
    "gnome-terminal-server", "kgx", "ptyxis", "konsole", "xfce4-terminal", "tilix", "terminator", "mate-terminal",
    "lxterminal", "kitty", "alacritty", "wezterm-gui", "foot", "xterm", "urxvt", "st", "ghostty",
    "windowsterminal.exe", "openconsole.exe", "conhost.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "wezterm-gui.exe", "alacritty.exe", "mintty.exe",
    "com.apple.terminal", "com.googlecode.iterm2", "net.kovidgoyal.kitty", "org.alacritty", "io.alacritty",
    "com.github.wez.wezterm", "dev.warp.warp-stable", "com.mitchellh.ghostty",
}


def is_terminal(app):
    """Whether the focused app (as an adapter names it) is a terminal."""
    return bool(app) and app.lower() in TERMINALS


def tail(text):
    """The last lines of a screen: trailing blanks and the padding consoles add are dropped."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines[-MAX_LINES:])[-MAX_CHARS:]


def read(app=None):
    """The focused terminal's last lines, or None (not a terminal, nothing readable, no permission)."""
    try:
        if sys.platform.startswith("linux"):
            text = read_atspi(app)
        elif sys.platform == "win32":
            text = read_uia(app)
        elif sys.platform == "darwin":
            text = read_ax(app)
        else:
            text = None
    except Exception:
        return None  # accessibility is a best effort: the instruction goes ahead without it
    return tail(text) if text and text.strip() else None


def read_atspi(app):
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    deadline = time.monotonic() + BUDGET_SECONDS
    desktop = Atspi.get_desktop(0)

    def focused_terminal(node, depth):
        if time.monotonic() > deadline or depth > 12:
            return None
        states = node.get_state_set()
        if not states.contains(Atspi.StateType.SHOWING) and depth > 1:
            return None
        if states.contains(Atspi.StateType.FOCUSED):
            return node if node.get_role() == Atspi.Role.TERMINAL else None
        for index in range(min(node.get_child_count(), 200)):
            found = focused_terminal(node.get_child_at_index(index), depth + 1)
            if found is not None:
                return found
        return None

    for index in range(desktop.get_child_count()):
        application = desktop.get_child_at_index(index)
        if app and application.get_name() != app:
            continue
        terminal = focused_terminal(application, 0)
        if terminal is not None:
            return Atspi.Text.get_text(terminal, 0, Atspi.Text.get_character_count(terminal))
    return None


def read_uia(app):
    """UI Automation, by vtable index (UIAutomationClient.h), so the service needs no comtypes."""
    import ctypes

    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

    def guid(text):
        value = GUID()
        ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(value))
        return value

    out = ctypes.POINTER(ctypes.c_void_p)

    def call(pointer, index, types, *arguments):
        vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *types)(vtable[index])(pointer, *arguments)

    def release(pointer):
        if pointer:
            vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])(pointer)

    ole32, oleaut32 = ctypes.oledll.ole32, ctypes.windll.oleaut32
    oleaut32.SysFreeString.argtypes = [ctypes.c_void_p]
    try:
        ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
    except OSError:
        pass  # already initialized on this thread
    automation, element, pattern, document = (ctypes.c_void_p() for _ in range(4))
    try:
        ole32.CoCreateInstance(ctypes.byref(guid("{ff48dba4-60ef-4201-aa87-54103eef594e}")), None, 1,
                               ctypes.byref(guid("{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}")), ctypes.byref(automation))
        call(automation, 8, [out], ctypes.byref(element))  # IUIAutomation::GetFocusedElement
        if not element:
            return None
        name = ctypes.c_void_p()
        call(element, 30, [out], ctypes.byref(name))  # IUIAutomationElement::get_CurrentClassName
        class_name = ctypes.wstring_at(name.value) if name.value else ""
        oleaut32.SysFreeString(name)
        # Windows Terminal's TermControl, or a classic console's text area; another app's focused
        # element is its own business.
        if class_name != "TermControl" and not is_terminal(app):
            return None
        call(element, 14, [ctypes.c_int, ctypes.POINTER(GUID), out], 10014,
             ctypes.byref(guid("{32eba289-3583-42c9-9c59-3b6d9a1e9b6a}")), ctypes.byref(pattern))  # GetCurrentPatternAs(UIA_TextPatternId, IID_IUIAutomationTextPattern)
        if not pattern:
            return None
        call(pattern, 7, [out], ctypes.byref(document))  # IUIAutomationTextPattern::get_DocumentRange
        text = ctypes.c_void_p()
        call(document, 12, [ctypes.c_int, out], -1, ctypes.byref(text))  # IUIAutomationTextRange::GetText
        value = ctypes.wstring_at(text.value) if text.value else ""
        oleaut32.SysFreeString(text)
        return value
    finally:
        for pointer in (document, pattern, element, automation):
            release(pointer)


def read_ax(app):
    from AppKit import NSWorkspace
    from ApplicationServices import (AXIsProcessTrusted, AXUIElementCopyAttributeValue, AXUIElementCreateApplication,
                                     kAXFocusedUIElementAttribute, kAXValueAttribute)
    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    bundle = str(front.bundleIdentifier() or "") if front is not None else ""
    if not is_terminal(bundle) or not AXIsProcessTrusted():
        return None
    # The system-wide focused element fails (-25204) where the frontmost app's own answer works.
    error, focused = AXUIElementCopyAttributeValue(AXUIElementCreateApplication(front.processIdentifier()),
                                                   kAXFocusedUIElementAttribute, None)
    if error or focused is None:
        return None
    error, value = AXUIElementCopyAttributeValue(focused, kAXValueAttribute, None)
    return str(value) if not error and value else None
