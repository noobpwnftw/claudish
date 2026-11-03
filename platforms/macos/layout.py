"""The keyboard layout's own dead keys (UCKeyTranslate): which key is dead, its accent, and the
letter it makes with the next key, for any layout (Spanish ´, French ^, U.S. Option+e). IMK hands
an input method a dead key's spacing accent with no dead-key state, so the layout is asked."""
import ctypes

KEY_DOWN = 0  # kUCKeyActionDown
SPACE = 49
# NSEvent modifier flags -> the Carbon modifier bits UCKeyTranslate takes (>> 8).
CARBON = ((1 << 16, 0x04), (1 << 17, 0x02), (1 << 18, 0x10), (1 << 19, 0x08))  # Caps Lock, Shift, Control, Option


def framework(name):
    return ctypes.cdll.LoadLibrary("/System/Library/Frameworks/%s.framework/%s" % (name, name))


class Layout:
    """The current keyboard layout's key data, read for each key (the layout may change)."""
    def __init__(self):
        carbon, core = framework("Carbon"), framework("CoreFoundation")
        self.copy = carbon.TISCopyCurrentKeyboardLayoutInputSource
        self.copy.restype = ctypes.c_void_p
        self.property = carbon.TISGetInputSourceProperty
        self.property.restype, self.property.argtypes = ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_void_p]
        self.data_key = ctypes.c_void_p.in_dll(carbon, "kTISPropertyUnicodeKeyLayoutData")
        self.bytes = core.CFDataGetBytePtr
        self.bytes.restype, self.bytes.argtypes = ctypes.c_void_p, [ctypes.c_void_p]
        self.release = core.CFRelease
        self.release.argtypes = [ctypes.c_void_p]
        self.kind = carbon.LMGetKbdType
        self.kind.restype = ctypes.c_uint8
        self.translate_key = carbon.UCKeyTranslate
        self.translate_key.restype = ctypes.c_int32
        self.translate_key.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint32,
                                       ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
                                       ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]

    def translate(self, key, flags, state=0):
        """(text, dead-key state after it) for a key with these NSEvent flags; None if unknown."""
        source = self.copy()
        if not source:
            return None
        try:
            data = self.property(source, self.data_key)
            if not data:
                return None
            modifiers = sum(bit for flag, bit in CARBON if flags & flag)
            dead, length = ctypes.c_uint32(state), ctypes.c_ulong(0)
            text = (ctypes.c_uint16 * 8)()
            if self.translate_key(self.bytes(data), key, KEY_DOWN, modifiers, self.kind(), 0,
                                  ctypes.byref(dead), 8, ctypes.byref(length), text):
                return None
            return bytes(text)[:length.value * 2].decode("utf-16-le", errors="replace"), dead.value
        finally:
            self.release(source)

    def dead(self, key, flags):
        """The dead-key state a key starts and its accent alone, or None when it is not dead."""
        result = self.translate(key, flags)
        if not result or not result[1]:
            return None
        alone = self.translate(SPACE, 0, result[1])  # the accent, as a space after it types it
        return result[1], (alone[0] if alone and alone[0] else "")


LAYOUT = []


def layout():
    """The layout reader, or None where Carbon cannot be read (then the U.S. Option map is used)."""
    if not LAYOUT:
        try:
            LAYOUT.append(Layout())
        except (OSError, AttributeError, ValueError):
            LAYOUT.append(None)
    return LAYOUT[0]
