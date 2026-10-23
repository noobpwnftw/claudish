"""Screenshots of every state cd_AI shows in GNOME Shell on Wayland, for the visual pass (G45).

Run by gallery.sh, inside the same container as driver.py: the real installer, IBus started by
the shell, a native Wayland GTK app. Each state is set up with real keys and captured with GNOME
Shell's own Screenshot call (--unsafe-mode, test plumbing). Nothing is checked: the pictures are
the output, in /tmp/claudish-gnome/gallery/.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import driver  # noqa: E402  the rig's helpers: Keyboard, focus, state, shell_eval, wait_for

OUT = driver.WORK / "gallery"


def shot(name):
    time.sleep(0.6)  # let the shell draw the popup
    path = OUT / (name + ".png")
    subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell.Screenshot",
                    "--object-path", "/org/gnome/Shell/Screenshot", "--method", "org.gnome.Shell.Screenshot.Screenshot",
                    "false", "false", str(path)], capture_output=True)
    print("captured", path.name, flush=True)


def serve(profile):
    service = driver.background(sys.executable, "-m", "claudish", "serve", "--profile", profile, cwd=str(driver.SRC))
    def up():
        from urllib.request import urlopen
        try:
            return urlopen("http://127.0.0.1:18765/health", timeout=1).status == 200
        except OSError:
            return False
    driver.wait_for(up, what="the service")
    return service


def main():
    driver.WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    config = Path.home() / ".config/claudish"
    config.mkdir(parents=True, exist_ok=True)
    agent = [sys.executable, str(driver.SRC / "tests/fake_agent.py")]
    (config / "config.json").write_text(json.dumps({"profiles": {
        "desk": {"backend": "rules"},
        "agent": {"backend": "rules", "session_command": agent}}}))
    service = serve("desk")
    app = driver.background(sys.executable, str(driver.SRC / "tests/desktop/linux/app.py"), str(driver.STATE),
                            str(driver.COMMANDS), env=dict(os.environ, GDK_BACKEND="wayland"))
    driver.wait_for(lambda: driver.state(), what="test app")
    keys = driver.Keyboard()
    driver.wait_for(lambda: driver.shell_eval(
        'global.get_window_actors().some(a => a.meta_window.title == "Claudish test app")'), what="the app window")
    driver.shell_eval("Main.overview.hide()")
    driver.wait_for(lambda: driver.shell_eval("!Main.overview.visible && !Main.overview.animationInProgress"),
                    what="overview closed")
    driver.shell_eval('global.get_window_actors().map(a => a.meta_window).find(w => w.title == "Claudish test app")'
                      '.activate(global.get_current_time())')
    try:
        driver.focus("view")
        keys.type("Thanks for the review ")  # continue: the rest of the sentence after the caret
        time.sleep(1.2)
        shot("01-continue-suggestion")
        keys.press("ctrl+a", "BackSpace", "Shift_L")  # compose
        keys.type("this is very important")
        shot("02-compose-typing")
        keys.press("Tab")  # the rewrite in place
        time.sleep(0.8)
        shot("03-rewrite-in-place")
        keys.press("Escape", "Escape")
        keys.type("say hi")
        keys.press("Return")  # an instruction's drafts
        time.sleep(1.0)
        shot("04-instruct-drafts")
        keys.press("Escape", "Escape")
        service.terminate()
        service.wait(5)
        service = serve("agent")
        keys.type("is my branch clean?")
        keys.press("Return")  # an agent: progress, then a permission question
        time.sleep(0.5)
        shot("05-agent-progress")
        driver.wait_for(lambda: True, timeout=2)
        time.sleep(1.5)
        shot("06-agent-question")
        keys.press("Escape", "Escape")
    finally:
        app.terminate()
        service.terminate()


if __name__ == "__main__":
    main()
