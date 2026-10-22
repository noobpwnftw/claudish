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

from Quartz import (CGEventCreateKeyboardEvent, CGEventKeyboardSetUnicodeString, CGEventPost,
                    kCGHIDEventTap)

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


def post(code, text=None):
    for down in (True, False):
        event = CGEventCreateKeyboardEvent(None, code, down)
        if text is not None:
            CGEventKeyboardSetUnicodeString(event, len(text.encode("utf-16-le")) // 2, text)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.02)
    time.sleep(0.03)


def type_text(text):
    for char in text:
        post(49 if char == " " else 0, char)


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


def fresh_document():
    """Empty the test app's text view and bring it to the front."""
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
    fresh_document()
    type_text("probe")
    time.sleep(0.5)
    check("synthetic keys reach the app (no input method)", document(), "probe")
    if document() != "probe":
        print("key events are not delivered (Accessibility permission?); app state:", state())
        return 1

    # 2. Install and select cd_AI.
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "dist/macos/Claudish.app", TARGET, symlinks=True)
    print(sh("swift", str(HERE / "input_source.swift"), str(TARGET), BUNDLE_ID, check=False))
    fresh_document()
    current = sh("swift", str(HERE / "input_source.swift"), "--current")
    check("cd_AI is the selected input source", current.startswith(BUNDLE_ID), True)

    # 3. Continue: keys go straight in; the rest waits as grey marked text; Tab takes it.
    type_text("ls -la")
    time.sleep(0.5)
    check("cd_AI starts in continue: keys go straight in", document(), "ls -la")
    key("Down")  # the context starts over
    fresh_document()
    type_text("Thanks for the review ")
    wait_for(lambda: state().get("marked"))
    check("continue: the suggestion waits as marked text", state().get("marked"), "and then some—naturally.")
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
