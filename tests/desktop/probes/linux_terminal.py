"""Probe: find the focused terminal through AT-SPI and read its screen (no shell hook, no MCP).

docker build -t claudish-a11y-probe -f tests/desktop/probes/Dockerfile.linux tests/desktop/probes
docker run --rm -v "$PWD/tests/desktop/probes:/p:ro" claudish-a11y-probe dbus-run-session -- python3 /p/linux_terminal.py
(Dockerfile.linux builds on tests/desktop/linux's image, claudish-desktop-linux.)
"""
import os
import subprocess
import time

os.environ.update(DISPLAY=":99", GTK_A11Y="atspi")
subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1024x768x24"], stderr=subprocess.DEVNULL)
time.sleep(1)
subprocess.Popen(["/usr/libexec/at-spi-bus-launcher", "--launch-immediately"])
time.sleep(1)
# gnome-terminal-server is started by D-Bus activation, so D-Bus must know the display.
subprocess.run(["dbus-update-activation-environment", "DISPLAY=:99", "GTK_A11Y=atspi"])
subprocess.run(["gnome-terminal", "--", "bash", "--norc"])
time.sleep(4)
for line in ("cd /tmp", "gti status", "ls /nope"):
    subprocess.run(["xdotool", "type", "--delay", "30", line])
    subprocess.run(["xdotool", "key", "Return"])
    time.sleep(0.8)

import gi  # noqa: E402
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402


def terminals(node):
    try:
        role = node.get_role_name()
    except Exception:
        return
    if role == "terminal":
        yield node
    for index in range(node.get_child_count()):
        yield from terminals(node.get_child_at_index(index))


desktop = Atspi.get_desktop(0)
for index in range(desktop.get_child_count()):
    app = desktop.get_child_at_index(index)
    for terminal in terminals(app):
        started = time.monotonic()
        text = Atspi.Text.get_text(terminal, 0, Atspi.Text.get_character_count(terminal))
        focused = terminal.get_state_set().contains(Atspi.StateType.FOCUSED)
        print("app %s (pid %d), focused %s, %d chars in %.1f ms" % (
            app.get_name(), app.get_process_id(), focused, len(text), (time.monotonic() - started) * 1000))
        print(text.rstrip())
