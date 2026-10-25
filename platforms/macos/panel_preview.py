"""Draw every design-lab state with cd_AI's macOS panel, one at a time, from the same panel
descriptions the lab draws (claudish/web/lab-states.js, generated from composition.py), for
comparing the native renderer with design.html#macos state by state. Not part of the input method.

  python3 panel_preview.py [seconds per state]       # on a Mac: watch, or screenshot each

Each state's name is printed as it shows."""
import os
import sys

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory, NSDate, NSRunLoop, NSScreen

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.join(here, "..", "..")
sys.path[:0] = [here, root, os.path.join(root, "scripts")]
import lab_states  # noqa: E402
from panel import Panel  # noqa: E402


def pump(seconds):
    """Let AppKit draw while waiting."""
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    screen = NSScreen.mainScreen().visibleFrame()
    caret = ((screen.origin.x + 200, screen.origin.y + screen.size.height - 220), (2, 18))
    wait = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    panel, toast = Panel(), Panel(toast=True)
    for name, spec in lab_states.load(os.path.join(root, "claudish/web/lab-states.js")).items():
        shown = toast if name in lab_states.TOASTS else panel
        shown.show(caret, spec)
        print(name, flush=True)
        pump(wait)
        shown.hide()


if __name__ == "__main__":
    main()
