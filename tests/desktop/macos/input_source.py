"""Register, enable, and select an input method through Text Input Sources (Carbon, via ctypes and
PyObjC), so the rig needs no compiler.

python input_source.py /path/to/Claudish.app org.claudish.inputmethod.Claudish
python input_source.py --current
python input_source.py --select com.apple.keylayout.US
python input_source.py --enable org.claudish.inputmethod.Claudish
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
    if sys.argv[1] == "--enable":
        # macOS answers with a dialog ("Allow … to enable …?"); the caller waits for it.
        for source in sources(sys.argv[2]):
            print("enable", prop(source, "kTISPropertyInputSourceID"), carbon.TISEnableInputSource(source))
        return 0
    # Register if needed and try to select; never enable, which would ask the user. Each call is a
    # fresh process: Text Input Sources caches its list per process, so a process that started
    # before the user clicked Allow keeps seeing the old answer.
    path, bundle_id = sys.argv[1], sys.argv[2]
    if not sources(bundle_id):
        print("register:", carbon.TISRegisterInputSource(NSURL.fileURLWithPath_(path).__c_void_p__()))
    for _ in range(3):
        for source in sources(bundle_id):
            if prop(source, "kTISPropertyInputSourceIsSelectCapable"):
                if carbon.TISSelectInputSource(source) == 0 and current().startswith(bundle_id):
                    print("current:", current())
                    return 0
        time.sleep(0.5)
    print("current:", current())
    return 1

if __name__ == "__main__":
    sys.exit(main())
