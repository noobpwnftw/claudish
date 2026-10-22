"""Inside the container: real Xvfb, IBus, Claudish engine and service, a GTK app, and xdotool keys.

Run by run.sh under dbus-run-session. Exits non-zero if any scenario fails.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SRC = Path("/claudish")
WORK = Path("/tmp/claudish-desktop")
STATE, COMMANDS = WORK / "state.json", WORK / "commands"
results = []


def sh(*command, **options):
    return subprocess.run(command, check=True, capture_output=True, text=True, **options).stdout


def background(*command, **options):
    log = open(WORK / (Path(command[0]).name + ".log"), "a")
    return subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, **options)


def wait_for(predicate, timeout=10, what="condition"):
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


def focus(name):
    COMMANDS.write_text(name)
    wait_for(lambda: state().get("focus") == name, what="focus on " + name)
    time.sleep(0.2)


def key(*names):
    sh("xdotool", "key", "--delay", "40", *names)


def type_text(text):
    sh("xdotool", "type", "--delay", "40", text)


def settle(seconds=0.6):
    time.sleep(seconds)  # Debounce (180 ms) + engine poll (40 ms) + request.


def check(name, actual, expected):
    ok = actual == expected
    results.append((name, ok, actual, expected))
    print("%s %-44s %r" % ("PASS" if ok else "FAIL", name, actual) + ("" if ok else " (expected %r)" % expected),
          flush=True)


def scenarios():
    focus("entry")
    type_text("hello-world")
    settle()
    check("composition is not committed while typing", state()["entry"], "")
    key("Return")
    wait_for(lambda: state()["entry"], what="commit")
    check("Enter commits your wording, dash substituted", state()["entry"], "hello—world")

    focus("other")
    type_text("very important")
    settle()
    key("Tab")
    wait_for(lambda: state()["other"], what="candidate commit")
    check("Tab accepts the rewrite", state()["other"], "particularly crucial")

    focus("view")
    type_text("very")
    settle()
    type_text(" good")  # A newer edit invalidates the candidate for "very".
    key("Tab")
    time.sleep(0.2)
    check("Tab right after an edit commits nothing stale", state()["view"], "")
    settle()
    key("Tab")
    wait_for(lambda: state()["view"], what="fresh candidate")
    check("fresh candidate after the edit", state()["view"], "particularly good")

    focus("entry")
    key("ctrl+a", "BackSpace")
    type_text("keep me")
    focus("other")  # Focus moves while composing.
    time.sleep(0.4)
    check("focus change keeps composed text", state()["entry"], "keep me")

    focus("other")
    key("ctrl+a", "BackSpace")
    type_text("draft")
    key("ctrl+a")  # Shortcut: commit the wording, then let the app select all.
    time.sleep(0.3)
    check("Ctrl shortcut commits the wording first", state()["other"], "draft")
    key("BackSpace")
    time.sleep(0.3)
    check("...and the app received Ctrl+A (all selected)", state()["other"], "")

    focus("password")
    type_text("pass-word")
    time.sleep(0.3)
    check("password field bypasses the engine", state()["password"], "pass-word")


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    sh(sys.executable, str(SRC / "platforms/linux/install.py"))
    # A login session would load install.py's environment.d file; load the same file here.
    session = dict(line.strip().split("=", 1) for line in
                   (Path.home() / ".config/environment.d/90-claudish-ibus.conf").read_text().splitlines() if "=" in line)
    print("Session environment from install.py:", session, flush=True)
    os.environ.update(session, DISPLAY=":99", GTK_IM_MODULE="ibus", XMODIFIERS="@im=ibus", QT_IM_MODULE="ibus")
    background("Xvfb", ":99", "-screen", "0", "1024x768x24", "-nolisten", "tcp")
    wait_for(lambda: subprocess.run(["xdpyinfo"], capture_output=True).returncode == 0, what="Xvfb")
    service = background(sys.executable, "-m", "claudish", "serve", "--backend", "rules", cwd=str(SRC))
    background("ibus-daemon", "--replace", "--panel=disable", "--xim", "--verbose")
    wait_for(lambda: subprocess.run(["ibus", "address"], capture_output=True).returncode == 0
             and "claudish" in subprocess.run(["ibus", "list-engine"], capture_output=True, text=True).stdout,
             timeout=20, what="IBus to list the claudish engine")
    # The ibus CLI exits 1 for <layout>default</layout> (it runs setxkbmap with "default"),
    # although the engine switches; check the active engine instead.
    subprocess.run(["ibus", "engine", "claudish"], capture_output=True)
    wait_for(lambda: sh("ibus", "engine").strip() == "claudish", what="the claudish engine to be active")
    app = background(sys.executable, str(Path(__file__).with_name("app.py")), str(STATE), str(COMMANDS))
    wait_for(lambda: state(), what="test app")
    print("IBus %s, engine %s" % (sh("ibus", "version").strip(), sh("ibus", "engine").strip()), flush=True)
    try:
        scenarios()
    finally:
        app.terminate()
        service.terminate()
    failed = [name for name, ok, _, _ in results if not ok]
    print("\n%d/%d scenarios passed" % (len(results) - len(failed), len(results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
