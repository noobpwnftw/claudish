"""Draw every state of cd_AI's macOS panel and overlay at once, for the visual pass (G45): run it on a
Mac (python3 panel_preview.py [seconds]) and look, or screenshot it. Not part of the input method."""
import sys

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory, NSFont, NSMakeRect, NSScreen, NSTimer

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from panel import Overlay, Panel  # noqa: E402

app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
screen = NSScreen.mainScreen().visibleFrame()
left, top = screen.origin.x + 60, screen.origin.y + screen.size.height - 80


def caret(x, y):
    return ((x, y), (2, 18))


keep = []
drafts = Panel()
drafts.show(caret(left, top), items=["Heads-up: the deploy moves to Friday—more soon.",
                                     "Quick update—we're shipping Friday instead.",
                                     "Deploy slips to Friday. Details to follow."], hint="1–3: pick · Esc: back")
question = Panel()
question.show(caret(left + 520, top), title="The model asks: Did you mean git status?", items=["Yes", "No"],
              hint="1–2 · or type a reply")
answer = Panel()
answer.show(caret(left, top - 260), title="The model says: The linker cannot find tokenize: parse.o calls it, but "
            "no object file defines it. Add tokenize.o to the link line in the Makefile.",
            items=["Insert it", "Dismiss"], hint="1–2")
helper = Panel()
helper.show(caret(left + 520, top - 260), title="Send this task to claude? Fix the link error in the build",
            items=["Yes", "No"], hint="opens in a new window")
hint = Panel()
hint.show(caret(left, top - 470), hint="Tab: keep · Esc: undo")
overlay = Overlay()
overlay.show(caret(left + 520, top - 470), "and then some—naturally.", NSFont.systemFontOfSize_(14))
keep += [drafts, question, answer, helper, hint, overlay]
NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
    float(sys.argv[1]) if len(sys.argv) > 1 else 30, app, "terminate:", None, False)
app.run()
