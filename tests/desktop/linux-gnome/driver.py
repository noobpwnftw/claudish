"""Inside the systemd container, as the user: real GNOME Shell on Wayland (headless), IBus started by
the shell, the Claudish engine registered by the real installer, a native Wayland GTK app, and keys
typed through Mutter's RemoteDesktop API. Exits non-zero if any scenario fails.

Run by run.sh. The app's input goes through Wayland text-input to GNOME Shell and then to IBus,
which is the path on Ubuntu and Fedora desktops; the X11 container test does not cover it.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import gi
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib

SRC = Path("/claudish")
WORK = Path("/tmp/claudish-gnome")
STATE, COMMANDS = WORK / "state.json", WORK / "commands"
results = []


def background(*command, **options):
    log = open(WORK / (Path(command[0]).name + ".log"), "a")
    return subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, **options)


def wait_for(predicate, timeout=15, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise TimeoutError("timed out waiting for " + what)


def state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def check(name, actual, expected):
    ok = actual == expected
    results.append((name, ok))
    print("%s %-46s %r" % ("PASS" if ok else "FAIL", name, actual) + ("" if ok else " (expected %r)" % expected),
          flush=True)


class Keyboard:
    """Keys through org.gnome.Mutter.RemoteDesktop, as GNOME's own remote desktop sends them."""

    def __init__(self):
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        manager = Gio.DBusProxy.new_sync(bus, 0, None, "org.gnome.Mutter.RemoteDesktop",
                                         "/org/gnome/Mutter/RemoteDesktop", "org.gnome.Mutter.RemoteDesktop", None)
        path = manager.call_sync("CreateSession", None, 0, -1, None).unpack()[0]
        self.session = Gio.DBusProxy.new_sync(bus, 0, None, "org.gnome.Mutter.RemoteDesktop", path,
                                              "org.gnome.Mutter.RemoteDesktop.Session", None)
        self.session.call_sync("Start", None, 0, -1, None)

    def keysym(self, value, pressed):
        self.session.call_sync("NotifyKeyboardKeysym", GLib.Variant("(ub)", (value, pressed)), 0, -1, None)

    def press(self, *names, delay=0.04):
        """Key names such as "Return", "F7", "ctrl+a" (held modifiers, then the key)."""
        for name in names:
            values = [Gdk.KEY_Control_L if part == "ctrl" else Gdk.keyval_from_name(part) for part in name.split("+")]
            for value in values:
                self.keysym(value, True)
            for value in reversed(values):
                self.keysym(value, False)
            time.sleep(delay)

    def click(self):
        """A left click where the pointer is (the middle of the screen, where GNOME places a new window)."""
        self.session.call_sync("NotifyPointerMotionRelative", GLib.Variant("(dd)", (0.0, 0.0)), 0, -1, None)
        for pressed in (True, False):
            self.session.call_sync("NotifyPointerButton", GLib.Variant("(ib)", (0x110, pressed)), 0, -1, None)  # BTN_LEFT

    def type(self, text, delay=0.04):
        for char in text:
            value = Gdk.unicode_to_keyval(ord(char))
            self.keysym(value, True)
            self.keysym(value, False)
            time.sleep(delay)


def focus(name):
    COMMANDS.write_text(name)
    wait_for(lambda: state().get("focus") == name, what="focus on " + name)
    time.sleep(0.3)


def settle(seconds=0.8):
    time.sleep(seconds)


def scenarios(keys):
    focus("entry")
    keys.type("hello-world")
    settle()
    check("composition is not committed while typing", state()["entry"], "")
    keys.press("Return")
    wait_for(lambda: state()["entry"], what="commit")
    check("Enter commits your wording, dash substituted", state()["entry"], "hello—world")

    focus("other")
    keys.type("very important")
    settle()
    keys.press("Tab")
    wait_for(lambda: state()["other"], what="candidate commit")
    check("Tab accepts the rewrite", state()["other"], "particularly crucial")

    focus("entry")
    keys.press("ctrl+a", "BackSpace")
    keys.type("keep me")
    focus("other")  # focus moves while composing
    time.sleep(0.5)
    check("focus change keeps composed text", state()["entry"], "keep me")

    focus("entry")
    keys.press("ctrl+a", "BackSpace")
    keys.press("F7")  # continue: typing goes straight in
    keys.type("Only my words")
    settle()
    focus("other")  # the suggestion must never be committed by a focus change
    time.sleep(0.5)
    check("continue: focus change keeps only your words", state()["entry"], "Only my words")
    focus("entry")
    keys.press("ctrl+a", "BackSpace")
    keys.type("Thanks for the review")
    settle()
    keys.press("Tab")
    wait_for(lambda: state()["entry"].endswith("."), what="continuation")
    check("continue: Tab takes the rest", state()["entry"], "Thanks for the review and then some—naturally.")

    focus("view")
    keys.press("F7")  # instruct
    keys.type("say hi")
    keys.press("Return")
    settle()
    check("instruct holds the text until it is inserted", state()["view"], "")
    keys.press("Return")
    wait_for(lambda: state()["view"], what="instruct result")
    check("instruct: Enter sends, Enter inserts", state()["view"], "As requested—say hi.")

    focus("password")
    keys.type("pass-word")
    time.sleep(0.5)
    check("password field bypasses the engine", state()["password"], "pass-word")


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    config = Path.home() / ".config/claudish"
    config.mkdir(parents=True, exist_ok=True)
    (config / "config.json").write_text(json.dumps({"profiles": {"desk": {"backend": "rules"}}}))
    # GNOME opens the Activities overview at login; close it, as a user would, so the app gets focus.
    subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell", "--object-path", "/org/gnome/Shell",
                    "--method", "org.freedesktop.DBus.Properties.Set", "org.gnome.Shell", "OverviewActive",
                    "<false>"], capture_output=True)
    service = background(sys.executable, "-m", "claudish", "serve", "--profile", "desk", cwd=str(SRC))
    app = background(sys.executable, str(SRC / "tests/desktop/linux/app.py"), str(STATE), str(COMMANDS),
                     env=dict(os.environ, GDK_BACKEND="wayland"))
    wait_for(lambda: state(), what="test app")
    keys = Keyboard()
    time.sleep(1.0)
    keys.click()  # activate the window, as a user would; Wayland gives new windows no focus by themselves
    engine = subprocess.run(["ibus", "engine"], capture_output=True, text=True).stdout.strip()
    print("IBus engine:", engine or "(none)", flush=True)
    try:
        scenarios(keys)
    finally:
        app.terminate()
        service.terminate()
    failed = [name for name, ok in results if not ok]
    print("\n%d/%d GNOME Wayland scenarios passed" % (len(results) - len(failed), len(results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
