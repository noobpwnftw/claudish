"""Register, enable, and select an input method through Text Input Sources, for the rig: a thin
command line over platforms/macos/sources.py (what the installer uses), so the rig needs no compiler.

python input_source.py /path/to/Claudish.app org.claudish.inputmethod.Claudish
python input_source.py --current
python input_source.py --select com.apple.keylayout.US
python input_source.py --enable org.claudish.inputmethod.Claudish
"""
import sys
from pathlib import Path

from Foundation import NSDictionary

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "platforms/macos"))
from sources import carbon, constant, current, enable, prop, register, select, sources, wrap  # noqa: E402


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
        for source, status in zip(sources(sys.argv[2]), enable(sys.argv[2])):
            print("enable", prop(source, "kTISPropertyInputSourceID"), status)
        return 0
    # Register if needed and try to select; never enable, which would ask the person.
    path, bundle_id = sys.argv[1], sys.argv[2]
    print("register:", register(path, bundle_id))
    selected = select(bundle_id)
    print("current:", current())
    return 0 if selected else 1


if __name__ == "__main__":
    sys.exit(main())
