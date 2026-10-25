"""One real IBus/GTK typing scenario in a disposable Docker desktop, within five seconds."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

SRC = Path("/claudish")
WORK = Path("/tmp/claudish-rig")
STATE, COMMANDS = WORK / "state.json", WORK / "commands"
DEADLINE = time.monotonic() + 4.5
children = []


def run(*args, check=True):
    return subprocess.run(args, capture_output=True, text=True, check=check,
                          timeout=max(0.1, min(1, DEADLINE - time.monotonic()))).stdout.strip()


def start(*args):
    with (WORK / (Path(args[0]).name + ".log")).open("a") as log:
        child = subprocess.Popen(args, cwd=SRC, stdout=log, stderr=subprocess.STDOUT)
    children.append(child)
    return child


def wait(predicate, what):
    while time.monotonic() < DEADLINE:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("timed out: " + what)


def state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def focus(field):
    COMMANDS.write_text(field)
    wait(lambda: state().get("focus") == field and state().get("active"), "focus " + field)


def key(*names):
    run("xdotool", "key", "--delay", "15", *names)


def type_text(text):
    run("xdotool", "type", "--clearmodifiers", "--delay", "10", text)


def health():
    try:
        with urlopen("http://127.0.0.1:18765/health", timeout=0.1) as response:
            return response.status == 200
    except OSError:
        return False


def setup(name):
    WORK.mkdir()
    os.environ.update(DISPLAY=":99", GTK_IM_MODULE="ibus", QT_IM_MODULE="ibus", XMODIFIERS="@im=ibus",
                      CLAUDISH_TRACE=str(WORK / "engine.log"), PYTHONDONTWRITEBYTECODE="1")
    # Use the actual per-user installer, then load the environment a new login would read.
    run(sys.executable, str(SRC / "platforms/linux/install.py"))
    session = Path.home() / ".config/environment.d/90-claudish-ibus.conf"
    os.environ.update(line.split("=", 1) for line in session.read_text().splitlines() if "=" in line)
    config = Path.home() / ".config/claudish/config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"profile": "rig", "profiles": {"rig": {"backend": "rules"}}}))
    start("Xvfb", ":99", "-screen", "0", "1024x768x24", "-nolisten", "tcp")
    wait(lambda: run("xdpyinfo", check=False), "Xvfb")
    service = start(sys.executable, "-m", "claudish", "serve")
    wait(health, "service")
    start("ibus-daemon", "--replace", "--panel=disable", "--xim")
    wait(lambda: "claudish" in run("ibus", "list-engine", check=False), "IBus registration")
    run("ibus", "engine", "claudish", check=False)  # layout=default can return 1 after switching
    wait(lambda: run("ibus", "engine", check=False) == "claudish", "active engine")
    qt = name.startswith("qt-")
    start(sys.executable, str(Path(__file__).with_name("app_qt.py" if qt else "app.py")),
          str(STATE), str(COMMANDS))
    wait(state, "test app")
    title = "Claudish Qt test app" if qt else "Claudish test app"
    window = run("xdotool", "search", "--onlyvisible", "--name", title).splitlines()[-1]
    run("xdotool", "windowfocus", window)
    focus("qline" if qt else "entry")
    return service


def scenario(name, service):
    if name == "qt-selection":
        COMMANDS.write_text("qline seed-selection")
        wait(lambda: state().get("qline") == "this is very important", "selected text fixture")
        key("Tab")
        wait(lambda: state().get("qline") == "this is very " and state().get("preedit"),
             "selected text becomes composition")
        key("Escape", "Escape")
        wait(lambda: state().get("qline") == "this is very important" and not state().get("preedit"),
             "Esc restores selected text")
        return

    if name == "password":
        focus("password")
        type_text("pass-word")
        wait(lambda: state().get("password") == "pass-word", "password bypass")
        assert not state().get("preedit"), state()
        return

    type_text("very important" if name == "compose" else "keep me")
    wait(lambda: state().get("preedit"), "composition")
    assert state()["entry"] == "", state()
    if name == "compose":
        key("Tab")
        trace = WORK / "engine.log"
        wait(lambda: trace.exists() and "result" in trace.read_text(), "rewrite result")
        key("Tab")
        wait(lambda: state().get("entry") == "particularly crucial", "explicit rewrite acceptance")
    elif name == "focus":
        focus("other")
        wait(lambda: state().get("entry") == "keep me", "composition committed on focus change")
        assert state()["other"] == "", state()
    else:
        if name == "offline":
            service.terminate()
            service.wait(timeout=0.5)
            key("Tab")
            time.sleep(0.25)
            assert state()["entry"] == "", state()
            assert state()["preedit"] == "keep me", state()
        key("Return")  # Enter keeps your words (Shift+Enter would ask)
        wait(lambda: state().get("entry") == "keep me", "original words committed")


def main():
    try:
        service = setup(sys.argv[1])
        scenario(sys.argv[1], service)
        print("PASS %s: real IBus + %s (%.2f s remaining)" %
              (sys.argv[1], "Qt" if sys.argv[1].startswith("qt-") else "GTK", DEADLINE - time.monotonic()))
    except Exception:
        for log in WORK.glob("*.log"):
            print("%s:\n%s" % (log.name, log.read_text()[-2500:]), file=sys.stderr)
        raise
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()


if __name__ == "__main__":
    main()
