"""Draw every design-lab state with cd_AI's macOS panel, one at a time, from the same panel
descriptions the lab draws (claudish/web/lab-states.js, generated from composition.py), for
comparing the native renderer with design.html#macos state by state. Not part of the input method.

  python3 panel_preview.py [seconds per state]       # on a Mac: watch, or screenshot each

Each state is announced in /tmp/claudish-gallery-state (the gallery protocol); with an answer in
/tmp/claudish-gallery-ack it moves on at once."""
import os
import sys
import time
from pathlib import Path

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory, NSDate, NSRunLoop, NSScreen

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.join(here, "..", "..")
sys.path[:0] = [here, root, os.path.join(root, "scripts")]
import lab_states  # noqa: E402
from panel import Panel  # noqa: E402

STATE, ACK = Path("/tmp/claudish-gallery-state"), Path("/tmp/claudish-gallery-ack")


def pump(seconds):
    """Let AppKit draw while waiting."""
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    screen = NSScreen.mainScreen().visibleFrame()
    caret = ((screen.origin.x + 200, screen.origin.y + screen.size.height - 220), (2, 18))
    wait = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0  # or until the gallery answers
    panel, toast = Panel(), Panel(toast=True)
    for name, spec in lab_states.load(os.path.join(root, "claudish/web/lab-states.js")).items():
        shown = toast if name in lab_states.TOASTS else panel
        shown.show(caret, spec)
        pump(0.3)
        ACK.unlink(missing_ok=True)
        STATE.write_text(name)
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and not ACK.exists():
            pump(0.1)
        shown.hide()
    STATE.write_text("done")


if __name__ == "__main__":
    main()
