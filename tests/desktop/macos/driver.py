"""Real typing on macOS (GitHub's macOS runners are Apple hardware): the built input method,
selected through Text Input Sources, typing into a test app (app.py) with Quartz key events.

Run on a Mac with the bundle built (platforms/macos/build.py) and the service running with the
rules backend (python -m claudish serve --backend rules). Needs pyobjc-framework-Quartz.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from Quartz import (CGEventCreateKeyboardEvent, CGEventGetFlags, CGEventKeyboardSetUnicodeString,
                    CGEventPost, CGEventSetFlags, kCGEventFlagMaskShift, kCGHIDEventTap)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BUNDLE_ID = "org.claudish.inputmethod.Claudish"
TARGET = Path.home() / "Library/Input Methods/Claudish.app"
results = []


def sh(*command, check=True):
    done = subprocess.run(command, capture_output=True, text=True)
    if check and done.returncode:
        raise RuntimeError("%s failed: %s %s" % (command[0], done.stdout, done.stderr))
    return done.stdout.strip()


# US ANSI key codes: a key event with a real key code goes through the input method, like a key
# press; an event carrying only a Unicode string reaches the app as inserted text.
US = dict(zip("asdfhgzxcv bqweryt123465=97-80]ou[ip lj'k;\\,/nm. `",
              [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, None, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
               24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, None, 37, 38, 39, 40, 41, 42, 43, 44, 45,
               46, 47, None, 50]))
US[" "] = 49
SHIFTED = dict(zip('!@#$%^&*()_+{}|:"<>?~', "1234567890-=[]\\;',./`"))


class Unfocused(RuntimeError):
    pass


def post(code, text=None, shift=False):
    # Keys go wherever focus is: if the test app is not in front, stop rather than type into
    # whatever is (a function key there is a system shortcut).
    if STATE.exists() and not state().get("active") and not front():
        raise Unfocused("the test app lost focus; stopping before typing elsewhere")
    for down in (True, False):
        event = CGEventCreateKeyboardEvent(None, code, down)
        # Keep the flags macOS gives the key (function keys carry Fn), but Shift only when asked:
        # otherwise a Shift from an earlier event sticks.
        flags = CGEventGetFlags(event) & ~kCGEventFlagMaskShift
        CGEventSetFlags(event, flags | (kCGEventFlagMaskShift if shift else 0))
        if text is not None:
            CGEventKeyboardSetUnicodeString(event, len(text.encode("utf-16-le")) // 2, text)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.02)
    time.sleep(0.03)


def type_text(text):
    for char in text:
        base = SHIFTED.get(char, char.lower())
        post(US[base], shift=char.isupper() or char in SHIFTED)


KEYS = {"Tab": 48, "Return": 36, "Escape": 53, "F7": 98, "Down": 125}


def key(name):
    post(KEYS[name])


WORK = Path(tempfile.mkdtemp())
STATE, COMMANDS = WORK / "state.json", WORK / "commands"


def state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def document():
    return state().get("text", "")


def front():
    """Bring the test app to the front. The consent dialog leaves System Settings in front, and a
    click on the Mac can leave anything there, so close System Settings and ask the app to activate
    until it is active."""
    subprocess.run(["pkill", "-x", "System Settings"], check=False)
    for _ in range(3):
        COMMANDS.write_text("focus")
        if wait_for(lambda: not COMMANDS.read_text() and state().get("active"), timeout=5):
            return True
        time.sleep(1)
    print(">>> the test window is not in front: click it on the Mac", flush=True)
    return wait_for(lambda: state().get("active"), timeout=60)


def fresh_document():
    """Empty the test app's text view and bring it to the front."""
    front()
    COMMANDS.write_text("clear")
    wait_for(lambda: not COMMANDS.read_text())
    time.sleep(0.5)


def check(name, actual, expected):
    ok = actual == expected
    results.append(ok)
    print("%s %-46s %r" % ("PASS" if ok else "FAIL", name, actual) + ("" if ok else " (expected %r)" % expected),
          flush=True)


def wait_for(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def main():
    COMMANDS.write_text("")
    app = subprocess.Popen([sys.executable, str(HERE / "app.py"), str(STATE), str(COMMANDS)])
    try:
        if not wait_for(lambda: state().get("active"), timeout=20):
            print("the test app did not become active:", state())
        return scenarios()
    finally:
        app.terminate()


def scenarios():
    # 1. Without the input method: can this session post keys to the app?
    print(sh(sys.executable, str(HERE / "input_source.py"), "--select", "com.apple.keylayout.US", check=False))
    fresh_document()
    type_text("probe")
    time.sleep(0.5)
    check("synthetic keys reach the app (no input method)", document(), "probe")
    if document() != "probe":
        print("key events are not delivered (Accessibility permission?); app state:", state())
        return 1

    # 2. Install and select cd_AI.
    # Replacing a registered bundle leaves macOS without a server to launch until it notices, so an
    # installed cd_AI is kept unless --reinstall asks for the fresh build.
    if not TARGET.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / "dist/macos/Claudish.app", TARGET, symlinks=True)
    elif "--reinstall" in sys.argv:
        # In place: a removed and re-added bundle is a new input source, which macOS asks about again.
        sh("rsync", "-a", "--delete", str(ROOT / "dist/macos/Claudish.app") + "/", str(TARGET) + "/")
        subprocess.run(["pkill", "-f", str(TARGET)], check=False)  # the next key starts the new build
    print(sh(sys.executable, str(HERE / "input_source.py"), str(TARGET), BUNDLE_ID, check=False))
    # macOS starts an input method at login; after an update (or a crash) it does not start it again
    # by itself, and keys then reach the app without it. Start it the way login would.
    if subprocess.run(["pgrep", "-f", str(TARGET / "Contents/MacOS")], capture_output=True).returncode:
        sh("open", "-g", str(TARGET))
        wait_for(lambda: not subprocess.run(["pgrep", "-f", str(TARGET / "Contents/MacOS")],
                                            capture_output=True).returncode, timeout=10)
    fresh_document()
    current = sh(sys.executable, str(HERE / "input_source.py"), "--current")
    check("cd_AI is the selected input source", current.startswith(BUNDLE_ID), True)

    # 3. Continue: keys go straight in; the rest waits as grey marked text; Tab takes it.
    type_text("ls -la")
    time.sleep(0.5)
    check("cd_AI starts in continue: keys go straight in", document(), "ls -la")
    running = not subprocess.run(["pgrep", "-f", str(TARGET / "Contents/MacOS")], capture_output=True).returncode
    check("cd_AI is running (the keys went through it)", running, True)
    key("Down")  # the context starts over
    fresh_document()
    type_text("Thanks for the review ")
    wait_for(lambda: state().get("marked"))
    check("continue: the suggestion waits as marked text", state().get("marked"), "and then some—naturally.")
    # KNOWN (ROADMAP G01): IMK drops the marked text's color on its way to the app, so the suggestion
    # is drawn like typed text; the fix is an overlay window after the caret.
    print("KNOWN continue: the suggestion is drawn in %s, not grey" % state().get("marked_color"))
    key("Tab")
    wait_for(lambda: document().endswith("naturally."))
    check("continue: Tab takes the suggestion", document(), "Thanks for the review and then some—naturally.")

    # 4. Instruct: F7, type, Enter sends, Enter inserts.
    key("Return")
    key("F7")
    type_text("say hi")
    key("Return")
    time.sleep(1.5)
    key("Return")
    wait_for(lambda: document().endswith("say hi."))
    check("instruct: Enter sends, Enter inserts", document().split("\n")[-1], "As requested—say hi.")

    print("%d/%d scenarios passed" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sh("screencapture", "-x", str(ROOT / "macos-typing.png"), check=False)
