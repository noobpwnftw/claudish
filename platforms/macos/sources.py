"""Text Input Sources (Carbon, via ctypes and PyObjC): register, enable and select an input method,
so the installer adds cd_AI without the person going to Settings (G61), and the rig does the same.

Each call should be a fresh process: Text Input Sources caches its list per process, so a process
that started before the person clicked Allow keeps seeing the old answer.
"""
import ctypes
import time

import objc
from Foundation import NSDictionary, NSURL

carbon = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Carbon.framework/Carbon")
P = ctypes.c_void_p
for name, restype, argtypes in (("TISRegisterInputSource", ctypes.c_int32, [P]),
                                ("TISCreateInputSourceList", P, [P, ctypes.c_bool]),
                                ("TISEnableInputSource", ctypes.c_int32, [P]),
                                ("TISSelectInputSource", ctypes.c_int32, [P]),
                                ("TISGetInputSourceProperty", P, [P, P]),
                                ("TISCopyCurrentKeyboardInputSource", P, [])):
    getattr(carbon, name).restype, getattr(carbon, name).argtypes = restype, argtypes


def constant(name):
    return P.in_dll(carbon, name).value


def wrap(pointer):
    return objc.objc_object(c_void_p=pointer) if pointer else None


def prop(source, key):
    return wrap(carbon.TISGetInputSourceProperty(source, constant(key)))


def current():
    return str(prop(carbon.TISCopyCurrentKeyboardInputSource(), "kTISPropertyInputSourceID"))


def sources(bundle_id):
    query = NSDictionary.dictionaryWithDictionary_({wrap(constant("kTISPropertyBundleID")): bundle_id})
    found = wrap(carbon.TISCreateInputSourceList(query.__c_void_p__(), True))
    return [item.__c_void_p__() for item in (found or [])]


def ids(bundle_id):
    return {str(prop(source, "kTISPropertyInputSourceID")) for source in sources(bundle_id)}


def register(path, bundle_id, modes=()):
    """Register the bundle's input sources if Text Input Sources does not know them yet, or not
    every one of its modes (an update that added one)."""
    known = ids(bundle_id)
    if not known or not set(modes) <= known:
        return carbon.TISRegisterInputSource(NSURL.fileURLWithPath_(path).__c_void_p__())
    return 0


def enable(bundle_id):
    """Enable those not enabled yet (macOS asks the person: "Allow … to enable …?"); a reinstall
    over an enabled cd_AI asks nothing. Returns the statuses."""
    return [carbon.TISEnableInputSource(source) for source in sources(bundle_id)
            if not prop(source, "kTISPropertyInputSourceIsEnabled")]


def select(bundle_id, tries=3):
    """Make the first selectable one the current input source; True when it is."""
    for _ in range(tries):
        for source in sources(bundle_id):
            if prop(source, "kTISPropertyInputSourceIsSelectCapable"):
                if carbon.TISSelectInputSource(source) == 0 and current().startswith(bundle_id):
                    return True
        time.sleep(0.5)
    return False
