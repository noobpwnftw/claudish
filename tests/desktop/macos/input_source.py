"""Register, enable, and select an input method through Text Input Sources (Carbon, via ctypes and
PyObjC), so the rig needs no compiler.

python input_source.py /path/to/Claudish.app org.claudish.inputmethod.Claudish
python input_source.py --current
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
    path, bundle_id = sys.argv[1], sys.argv[2]
    print("register:", carbon.TISRegisterInputSource(NSURL.fileURLWithPath_(path).__c_void_p__()))
    for attempt in range(1, 21):  # a newly registered input method can take a moment
        for source in sources(bundle_id):
            if not prop(source, "kTISPropertyInputSourceIsEnabled"):
                print("enable", prop(source, "kTISPropertyInputSourceID"), carbon.TISEnableInputSource(source))
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
