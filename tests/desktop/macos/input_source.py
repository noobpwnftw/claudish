"""Register, enable, and select an input method through Text Input Sources (Carbon, via ctypes and
PyObjC), so the rig needs no compiler.

python input_source.py /path/to/Claudish.app org.claudish.inputmethod.Claudish
python input_source.py --current
python input_source.py --select com.apple.keylayout.US
"""
import ctypes
import sys
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


def main():
    if sys.argv[1] == "--current":
        print(current())
        return 0
    if sys.argv[1] == "--select":
        query = NSDictionary.dictionaryWithDictionary_({wrap(constant("kTISPropertyInputSourceID")): sys.argv[2]})
        found = wrap(carbon.TISCreateInputSourceList(query.__c_void_p__(), False)) or []
        status = carbon.TISSelectInputSource(found[0].__c_void_p__()) if len(found) else -1
        print("select", sys.argv[2], status, "current:", current())
        return 0 if status == 0 else 1
    path, bundle_id = sys.argv[1], sys.argv[2]
    print("register:", carbon.TISRegisterInputSource(NSURL.fileURLWithPath_(path).__c_void_p__()))
    # Enabling a third-party input method asks the user (macOS: "Allow … to enable …?"): ask once,
    # then wait for the answer; asking again on every retry raises the dialog again.
    for source in sources(bundle_id):
        if not prop(source, "kTISPropertyInputSourceIsEnabled"):
            print("enable", prop(source, "kTISPropertyInputSourceID"), carbon.TISEnableInputSource(source))
    for attempt in range(1, 61):
        for source in sources(bundle_id):
            if prop(source, "kTISPropertyInputSourceIsSelectCapable"):
                status = carbon.TISSelectInputSource(source)
                print("attempt", attempt, "select", prop(source, "kTISPropertyInputSourceID"), status)
                if status == 0 and current().startswith(bundle_id):
                    print("current:", current())
                    return 0
        time.sleep(1)
    print("current:", current())
    return 1


if __name__ == "__main__":
    sys.exit(main())
