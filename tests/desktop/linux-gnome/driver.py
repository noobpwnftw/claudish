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
        # Headless GNOME has no keyboard until this session's virtual one sends a key, and a Wayland
        # seat without a keyboard gives no window keyboard focus: tap Shift to create it.
        self.press("Shift_L")

    def keysym(self, value, pressed):
        self.session.call_sync("NotifyKeyboardKeysym", GLib.Variant("(ub)", (value, pressed)), 0, -1, None)

    def press(self, *names, delay=0.04):
        """Key names such as "Return", "Shift_L", "ctrl+a" (held modifiers, then the key)."""
        for name in names:
            if name == "Shift_L":
                time.sleep(0.4)  # a Shift tap comes after a pause (a Shift right after a key is rolled typing)
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


def shell_eval(code):
    """Evaluate in GNOME Shell (test plumbing); returns the result as Python, or None on failure."""
    out = subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell", "--object-path", "/org/gnome/Shell",
                          "--method", "org.gnome.Shell.Eval", code], capture_output=True, text=True).stdout.strip()
    if not out.startswith("(true, "):
        return None
    try:
        return json.loads(eval(out[len("(true, "):-1]) or "null")  # gdbus prints a quoted JSON string
    except (SyntaxError, ValueError):
        return None


def indicator():
    """The text GNOME Shell's input source indicator shows (an engine's InputMode symbol)."""
    found = shell_eval("""(() => { const out = [];
        const walk = a => { if (a.visible && typeof a.text === 'string' && a.text) out.push(a.text);
                            (a.get_children ? a.get_children() : []).forEach(walk); };
        walk(Main.panel.statusArea.keyboard); return JSON.stringify(out); })()""")
    if isinstance(found, str):  # Eval hands back the JSON text
        found = json.loads(found)
    shown = set(found or [])
    return shown.pop() if len(shown) == 1 else sorted(shown)


def focus(name):
    COMMANDS.write_text(name)
    try:
        wait_for(lambda: state().get("focus") == name, what="focus on " + name)
    except TimeoutError:
        print("app state:", state(), "| shell focus:", shell_eval(
            "global.display.focus_window ? global.display.focus_window.title : null"), flush=True)
        raise
    time.sleep(0.3)


def settle(seconds=0.8):
    time.sleep(seconds)


def scenarios(keys):
    focus("entry")
    check("cd_AI starts in compose: the top bar shows it", indicator(), "AI")
    keys.type("hello-world")
    settle()
    check("compose: nothing is committed while typing", state()["entry"], "")
    keys.press("Shift_L+Return")
    wait_for(lambda: state()["entry"], what="commit")
    check("Shift+Enter keeps your words as typed", state()["entry"], "hello-world")
    keys.press("ctrl+a", "BackSpace")
    keys.press("Shift_L")  # a Shift tap: continue, which types like en_US
    time.sleep(0.4)
    check("a Shift tap: the top bar shows continue", indicator(), "cd")
    keys.type("ls -la")
    time.sleep(0.4)
    check("continue: keys go straight in, hyphens kept", state()["entry"], "ls -la")
    keys.press("ctrl+a", "BackSpace")
    keys.press("Shift_L")  # back to compose
    time.sleep(0.4)

    focus("other")
    keys.type("very important")
    keys.press("Tab")  # asks; the rewrite takes your words' place as it arrives
    settle()
    keys.press("Tab")  # keeps it
    wait_for(lambda: state()["other"], what="candidate commit")
    check("Tab rewrites, Tab keeps it", state()["other"], "particularly crucial")

    focus("view")
    keys.press("ctrl+a", "BackSpace")
    focus("entry")
    keys.press("ctrl+a", "BackSpace")
    keys.type("keep me")
    focus("view")  # focus moves while composing
    time.sleep(0.5)
    # GNOME commits the composition after GTK has moved focus, so it lands in the newly focused
    # field (the same for every input method that commits on focus-out). Claudish's guarantee
    # is that the words survive exactly once: never lost, never doubled.
    landed = state()
    check("focus change keeps your words exactly once", (landed["entry"] + landed["view"]).count("keep me"), 1)
    print("  (GNOME put them in the %s field)" % ("original" if landed["entry"] else "newly focused"), flush=True)
    focus("view")
    keys.press("ctrl+a", "BackSpace")

    focus("entry")
    keys.press("ctrl+a", "BackSpace")
    keys.press("Shift_L")  # continue: typing goes straight in
    keys.type("Only my words")
    settle()
    focus("other")  # the suggestion must never be committed by a focus change
    time.sleep(0.5)
    check("continue: focus change keeps only your words", state()["entry"], "Only my words")
    focus("entry")
    keys.press("ctrl+a", "BackSpace")
    keys.type("Thanks for the review ")  # a pause after a word: continue asks
    settle()
    keys.press("Tab")
    wait_for(lambda: state()["entry"].endswith("."), what="continuation")
    check("continue: Tab takes the rest", state()["entry"], "Thanks for the review and then some—naturally.")

    focus("view")
    keys.press("Shift_L")  # compose: Enter does it as an instruction
    keys.type("say hi")
    keys.press("Return")
    settle()
    check("instruct holds the text until it is inserted", state()["view"], "")
    keys.press("Return")  # a reflexive second Enter inserts nothing: Enter talks to the model
    settle()
    check("a second Enter inserts nothing", state()["view"], "")
    keys.press("Tab")  # Tab takes the model's text
    wait_for(lambda: state()["view"], what="instruct result")
    check("instruct: Enter sends, Tab inserts", state()["view"], "As requested—say hi.")

    focus("password")
    keys.type("pass-word")
    time.sleep(0.5)
    check("password field bypasses the engine", state()["password"], "pass-word")


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    config = Path.home() / ".config/claudish"
    config.mkdir(parents=True, exist_ok=True)
    (config / "config.json").write_text(json.dumps({"profiles": {"desk": {"backend": "rules"}}}))
    service = background(sys.executable, "-m", "claudish", "serve", "--profile", "desk", cwd=str(SRC))
    app = background(sys.executable, str(SRC / "tests/desktop/linux/app.py"), str(STATE), str(COMMANDS),
                     env=dict(os.environ, GDK_BACKEND="wayland"))
    wait_for(lambda: state(), what="test app")
    keys = Keyboard()
    # GNOME opens the Activities overview at login and gives a new window no focus by itself; do
    # what a user's first click does: leave the overview and activate the window (Eval needs
    # --unsafe-mode, which run.sh passes; it is test plumbing, not part of what is tested).
    wait_for(lambda: shell_eval('global.get_window_actors().some(a => a.meta_window.title == "Claudish test app")'),
             what="the app window")
    shell_eval("Main.overview.hide()")
    wait_for(lambda: shell_eval("!Main.overview.visible && !Main.overview.animationInProgress"), what="overview closed")
    shell_eval('global.get_window_actors().map(a => a.meta_window).find(w => w.title == "Claudish test app")'
               '.activate(global.get_current_time())')
    wait_for(lambda: shell_eval('global.display.focus_window && global.display.focus_window.title == "Claudish test app"'),
             what="the app window to have focus")
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
