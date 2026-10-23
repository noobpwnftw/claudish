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


TRACE = Path("/tmp/claudish-engine-trace.log")


def check(name, actual, expected):
    ok = actual == expected
    if not ok and TRACE.exists():
        print("".join(TRACE.read_text().splitlines(True)[-25:]), end="", flush=True)
    results.append((name, ok, actual, expected))
    print("%s %-44s %r" % ("PASS" if ok else "FAIL", name, actual) + ("" if ok else " (expected %r)" % (expected,)),
          flush=True)


def doctor():
    out = subprocess.run([sys.executable, "-m", "claudish", "doctor", "--json"], capture_output=True, text=True,
                         cwd=str(SRC)).stdout
    return json.loads(out)


def scenarios():
    focus("entry")
    type_text("ls -la")  # switching to cd_AI types like en_US: straight in, nothing changed
    time.sleep(0.3)
    check("cd_AI starts in continue: keys go straight in", state()["entry"], "ls -la")
    key("ctrl+a", "BackSpace")
    key("shift")  # a Shift tap: continue -> compose
    type_text("hello-world")
    settle()
    check("composition is not committed while typing", state()["entry"], "")
    key("shift+Return")
    wait_for(lambda: state()["entry"], what="commit")
    check("Shift+Enter keeps your words, dash substituted", state()["entry"], "hello—world")

    focus("other")
    type_text("very important")
    key("Tab")  # asks; the rewrite takes your words' place as it arrives, still a composition
    wait_for(lambda: state().get("preedit") == "particularly crucial", what="the rewrite in place")
    check("Tab converts the rewrite in place", (state().get("preedit"), state()["other"]),
          ("particularly crucial", ""))
    key("Escape")  # your words again
    wait_for(lambda: state().get("preedit") == "very important", what="your words again")
    check("Esc brings your words back", state().get("preedit"), "very important")
    key("Tab", "Tab")  # the rewrite again (no new request), then kept
    wait_for(lambda: state()["other"], what="candidate commit")
    check("Tab again keeps the rewrite", state()["other"], "particularly crucial")

    focus("view")
    type_text("very")
    settle()
    check("rewrite asks nothing while you type", state().get("preedit"), "very")
    type_text(" good")
    key("Tab")
    time.sleep(0.2)
    check("Tab asks; nothing is committed", state()["view"], "")
    wait_for(lambda: state().get("preedit") == "particularly good", what="the rewrite of the whole phrase")
    key("Tab")
    wait_for(lambda: state()["view"], what="the rewrite kept")
    check("the rewrite is of everything typed", state()["view"], "particularly good")

    # Rewriting a selection needs the toolkit to report it: GTK3 and GTK4 (IBus 1.5.29) report the
    # anchor at the cursor, so Tab with a selection is the app's there (Qt does: qt_scenarios()).

    focus("entry")
    key("ctrl+a", "BackSpace")
    type_text("keep me")
    focus("other")  # Focus moves while composing.
    time.sleep(0.4)
    check("focus change keeps composed text", state()["entry"], "keep me")

    # Continue: the rest of the sentence shows greyed after the caret (ghost text).
    focus("entry")
    key("ctrl+a", "BackSpace")
    type_text("Thanks for the review ")  # a pause after a word: continue asks
    key("shift")  # compose -> continue: your words go in as typed
    # The grey suggestion is the preedit, which the app sees; before the tap lands it still holds the
    # composition, so wait for the suggestion itself.
    expected = "and then some—naturally."
    try:
        wait_for(lambda: state().get("preedit") == expected, what="the grey suggestion")
    except TimeoutError:
        pass
    check("continue: the suggestion waits after the caret", state().get("preedit"), expected)
    key("Tab")  # takes the rest
    wait_for(lambda: state()["entry"].endswith("naturally."), what="continuation")  # not just any text: it had some
    check("continue: Tab takes the ghost text", state()["entry"], "Thanks for the review and then some—naturally.")
    key("ctrl+a", "BackSpace")
    type_text("Only my words")
    settle()  # the ghost is showing now
    focus("other")  # a focus change must not commit a suggestion nobody accepted
    time.sleep(0.4)
    check("continue: focus change keeps only your words", state()["entry"], "Only my words")
    focus("entry")
    key("ctrl+a", "BackSpace")
    type_text("Keep typing")
    settle()
    type_text(" on")  # typing ignores the ghost
    key("Return")
    wait_for(lambda: state()["entry"], what="commit")
    check("continue: typing ignores the ghost", state()["entry"], "Keep typing on")
    key("shift")  # continue -> compose, for the scenarios below
    key("ctrl+a", "BackSpace")

    focus("other")
    key("ctrl+a", "BackSpace")
    type_text("draft")
    key("ctrl+a")  # Shortcut: commit the wording, then let the app select all.
    time.sleep(0.3)
    check("Ctrl shortcut commits the wording first", state()["other"], "draft")
    key("BackSpace")
    time.sleep(0.3)
    check("...and the app received Ctrl+A (all selected)", state()["other"], "")

    focus("view")
    key("ctrl+a", "BackSpace")
    type_text("say hi")  # still compose
    key("Return")  # Enter sends it as an instruction.
    settle()
    key("Tab")  # Tab accepts too.
    wait_for(lambda: state()["view"], what="instruct draft")
    check("Enter sends an instruction, Tab inserts", state()["view"], "As requested—say hi.")

    key("ctrl+a", "BackSpace")
    type_text("write a story")  # Still in instruct mode: held until Enter.
    settle()
    check("instruct holds the text while typing", state()["view"], "")
    key("Return")  # send
    settle()
    key("Return")  # insert
    wait_for(lambda: state()["view"], what="instruct result")
    check("Enter sends, the next Enter inserts", state()["view"], "As requested—write a story.")

    key("ctrl+a", "BackSpace")
    type_text("describe this")
    key("F8")  # look: the service captures this window with ImageMagick and sends it along
    key("Return")
    settle(1.5)
    key("Return")
    wait_for(lambda: state()["view"], what="instruct result with a window picture")
    check("F8 sends a real picture of the window", state()["view"], "As requested—describe this, having looked at the window.")

    key("ctrl+a", "BackSpace")
    type_text("greet")
    key("Return")  # three readings come back as a numbered list
    settle()
    key("2")
    wait_for(lambda: state()["view"], what="the second reading")
    check("2 inserts the second of several readings", state()["view"], "Certainly—as requested—greet.")

    key("ctrl+a", "BackSpace")
    type_text("greet")
    key("Return")
    settle()
    key("Escape")  # the drafts close; the instruction stays, to refine
    time.sleep(0.3)
    check("Esc closes the drafts and keeps the instruction", (state().get("preedit"), state()["view"]),
          ("greet", ""))
    key("Escape")  # and is dropped: nothing inserted
    time.sleep(0.3)
    check("Esc again drops the instruction", (state().get("preedit"), state()["view"]), ("", ""))

    check("binding for the focused app ran its context provider", (WORK / "bound-app.py").exists(), True)
    check("binding for another app did not run", (WORK / "bound-firefox").exists(), False)

    focus("password")
    type_text("pass-word")
    time.sleep(0.3)
    check("password field bypasses the engine", state()["password"], "pass-word")



QT_STATE, QT_COMMANDS = WORK / "qt-state.json", WORK / "qt-commands"


def qt_state():
    try:
        return json.loads(QT_STATE.read_text())
    except (OSError, ValueError):
        return {}


def qt_scenarios():
    """Qt (5, through the IBus input context plugin): typing, and rewriting a selection, which GTK
    cannot offer (it reports no selection anchor). Starts in compose, where scenarios() ends."""
    app = background(sys.executable, str(Path(__file__).with_name("app_qt.py")), str(QT_STATE), str(QT_COMMANDS))
    try:
        wait_for(qt_state, what="Qt test app")
        QT_COMMANDS.write_text("qline")
        wait_for(lambda: qt_state().get("focus") == "qline", what="focus on the Qt line edit")
        time.sleep(0.3)
        type_text("very important")
        key("Tab")
        wait_for(lambda: qt_state().get("preedit") == "particularly crucial", what="the rewrite in Qt")
        key("Tab")
        wait_for(lambda: qt_state()["qline"], what="the Qt commit")
        check("Qt: Tab rewrites in place, Tab keeps it", qt_state()["qline"], "particularly crucial")
        key("ctrl+a", "BackSpace")
        key("shift")  # continue: straight in
        type_text("this is very important")
        key("shift")  # back to compose, with nothing composed
        time.sleep(0.3)
        QT_COMMANDS.write_text("qline select-last-word")
        wait_for(lambda: not QT_COMMANDS.read_text(), what="the Qt selection")
        time.sleep(0.3)
        key("Tab")  # the selection becomes the composition and is rewritten
        try:
            wait_for(lambda: qt_state().get("preedit"), what="the selection taken")
        except TimeoutError:
            pass
        check("Qt: Tab takes the selection to rewrite", (qt_state()["qline"], bool(qt_state().get("preedit"))),
              ("this is very ", True))
        key("Escape", "Escape")  # your words again, then back into the app as they were
        time.sleep(0.4)
        check("Qt: Esc puts the selection back", (qt_state()["qline"], qt_state().get("preedit")),
              ("this is very important", ""))
    finally:
        app.terminate()
        app.wait()
        # No window manager: give the GTK window the keyboard back.
        subprocess.run(["xdotool", "search", "--name", "^Claudish test app$", "windowfocus"])


def agent_session(service):
    """G18: restart the service with an agent profile (the scripted stream-json agent) and run a
    session at the caret: a partial draft, a permission question answered with 1, then Enter."""
    service.terminate()
    service.wait(timeout=5)
    service = background(sys.executable, "-m", "claudish", "serve", "--profile", "agent", cwd=str(SRC))
    wait_for(health, what="agent service")
    focus("view")
    key("ctrl+a", "BackSpace")
    type_text("is my branch clean")
    key("Return")  # starts the session
    time.sleep(2.0)  # partial draft, then the permission question
    check("the agent waits for an answer", state()["view"], "")
    key("1")  # Allow
    time.sleep(1.0)
    key("Return")  # insert the result
    wait_for(lambda: state()["view"], what="agent result")
    check("agent session: 1 allows the tool, Enter inserts", state()["view"], "The branch is clean—nothing to commit.")
    # Words instead of a number: the agent hears them as a refusal with your reason.
    key("ctrl+a", "BackSpace")
    type_text("is my branch clean")
    key("Return")
    time.sleep(2.0)
    type_text("use git diff")  # typed while the question shows: the reply, not the instruction
    time.sleep(0.3)
    check("typing while the agent asks composes a reply", (state().get("preedit"), state()["view"]),
          ("use git diff", ""))
    key("Return")  # sends the reply
    time.sleep(1.0)
    key("Return")  # inserts the result
    wait_for(lambda: state()["view"], what="agent result after a typed reply")
    check("a typed reply reaches the agent", state()["view"], "Understood—I left it alone. (use git diff)")
    return service


def surrounding_context(service):
    """Continue begins from the app's text before the caret (IBus surrounding text). The service
    never logs typed text, so a recording stub takes its port for this one check."""
    import http.server
    import threading
    service.terminate()
    service.wait(timeout=5)
    received, bodies = [], []

    class Stub(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"backend": "stub", "modes": ["continue", "instruct", "rewrite"]}')

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/suggest":
                received.append(body.get("text"))
                bodies.append(body)
                reply = {"text": body["text"] + "and then some.", "candidates": [body["text"] + "and then some."]}
                self.send_response(200)
            else:  # no agent sessions here
                reply = {"error": "no sessions"}
                self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(reply).encode())

    stub = http.server.ThreadingHTTPServer(("127.0.0.1", 18765), Stub)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    try:
        focus("other")
        key("ctrl+a", "BackSpace")
        type_text("Pasted words.")  # compose
        key("shift+Return")  # keeps your words: the field now holds text that was never typed in continue
        key("shift")  # compose -> continue, with nothing typed in continue yet
        type_text(" We ship ")
        wait_for(lambda: received, what="a continue request")
        check("continue begins from the text already there", received[-1], "Pasted words. We ship ")

        # A rewrite knows where it goes: the text box around the caret, and the app.
        focus("view")
        key("ctrl+a", "BackSpace")
        type_text("Dear Ana, ")
        key("shift")  # continue -> compose
        type_text("thanks")
        key("Tab")
        wait_for(lambda: bodies and bodies[-1].get("mode") == "rewrite", what="a rewrite request")
        sent = bodies[-1]
        check("a rewrite is sent with the text around it", (sent["text"], sent.get("before"), sent.get("app")),
              ("thanks", "Dear Ana, ", "app.py"))
        key("Escape", "Escape")

        # An email address field is not prose: nothing is suggested unasked.
        focus("email")
        key("shift")  # compose -> continue
        count = len(bodies)
        type_text("ana at example dot com ")
        time.sleep(1.0)
        check("an email field gets no unasked suggestions", len(bodies) - count, 0)
    finally:
        stub.shutdown()
        stub.server_close()


def health():
    try:
        from urllib.request import urlopen
        return urlopen("http://127.0.0.1:18765/health", timeout=1).status == 200
    except OSError:
        return False


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    status = lambda name: next((c["status"], c["fix"]) for c in doctor() if c["check"] == name)
    check("doctor: not installed yet", status("Input method")[0], "fail")
    sh(sys.executable, str(SRC / "platforms/linux/install.py"))
    # Installed, but this session predates the environment.d file: IBus cannot see the component.
    search_path = status("IBus search path")
    check("doctor: stale session flagged", (search_path[0], "log out and back in" in (search_path[1] or "")), ("fail", True))
    # A login session would load install.py's environment.d file; load the same file here.
    session = dict(line.strip().split("=", 1) for line in
                   (Path.home() / ".config/environment.d/90-claudish-ibus.conf").read_text().splitlines() if "=" in line)
    print("Session environment from install.py:", session, flush=True)
    os.environ.update(session, DISPLAY=":99", GTK_IM_MODULE="ibus", XMODIFIERS="@im=ibus", QT_IM_MODULE="ibus",
                      CLAUDISH_TRACE=str(TRACE))  # event kinds from the engine, printed when a check fails
    background("Xvfb", ":99", "-screen", "0", "1024x768x24", "-nolisten", "tcp")
    wait_for(lambda: subprocess.run(["xdpyinfo"], capture_output=True).returncode == 0, what="Xvfb")
    # A "supported text box": a binding for the test app (IBus reports it as gtk3-im:app.py) runs a
    # command provider that leaves a marker; a binding for another app must never run.
    config_dir = Path.home() / ".config/claudish"
    config_dir.mkdir(parents=True, exist_ok=True)
    marker = "import pathlib, sys; pathlib.Path(sys.argv[1]).touch(); print('context for ' + sys.argv[1])"
    agent = {"backend": "rules", "session_command": [sys.executable, str(SRC / "tests/fake_agent.py")]}
    (config_dir / "config.json").write_text(json.dumps({"profiles": {"agent": agent, "desk": {"backend": "rules", "bindings": [
        {"app": "app.py", "context": [{"type": "command", "ttl": 0,
                                        "command": [sys.executable, "-c", marker, str(WORK / "bound-app.py")]}]},
        {"app": "firefox*", "context": [{"type": "command", "ttl": 0,
                                          "command": [sys.executable, "-c", marker, str(WORK / "bound-firefox")]}]},
    ]}}}))
    service = background(sys.executable, "-m", "claudish", "serve", "--profile", "desk", cwd=str(SRC))
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
    statuses = {c["check"]: c["status"] for c in doctor()}
    # "Starts at login" is tested in tests/desktop/linux-systemd; here the harness starts the service.
    check("doctor: healthy session all green",
          sorted(c for c, s in statuses.items() if s in ("fail", "warn") and c != "Starts at login"), [])
    for marker in WORK.glob("bound-*"):  # doctor runs every provider to check it; start the binding test clean
        marker.unlink()
    try:
        scenarios()
        qt_scenarios()
        service = agent_session(service)
        surrounding_context(service)
    except TimeoutError:
        print("--- service log\n" + (WORK / "python3.log").read_text()[-3000:], flush=True)
        raise
    finally:
        app.terminate()
        service.terminate()
    failed = [name for name, ok, _, _ in results if not ok]
    print("\n%d/%d scenarios passed" % (len(results) - len(failed), len(results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
