"""Draw cd_AI's macOS panel in every state of the design lab at once (docs/design/design.md), from
real Composition states, for comparing with claudish/web/design.html#macos: run it on a Mac
(python3 panel_preview.py [seconds]) and screenshot it. Not part of the input method."""
import os
import sys

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory, NSScreen, NSTimer

here = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [here, os.path.join(here, "..", "..")]
from claudish.composition import Composition  # noqa: E402
from panel import Overlay, Panel  # noqa: E402

DRAFTS = ["Thank you for the invitation — I'm afraid I can't make the offsite this time.",
          "I'd love to join, but I won't be able to attend the offsite.",
          "Unfortunately the offsite clashes with a deadline, so I'll have to sit this one out."]


def composed(text):
    state = Composition()
    state.mode = "compose"
    state.change(text)
    return state


def states():
    """(name, spec) for each state the lab shows, built the way the input method builds them."""
    typing = composed("running late, start without me")
    yield "compose", typing.panel(typing.typed_at + 2)
    rewriting = composed("running late, start without me")
    rewriting.tab()
    yield "rewriting", rewriting.panel()
    rewriting.offer(rewriting.revision, "I'm running a little late — please start without me.")
    yield "converted", rewriting.panel()
    drafts = composed("decline the offsite politely")
    drafts.submit()
    drafts.offer(drafts.revision, DRAFTS[0], DRAFTS[1:])
    yield "drafts", drafts.panel()
    drafts.hosted = "Claude"
    yield "hosted", drafts.panel()
    asked = composed("summarize this thread")
    asked.submit()
    asked.ask(asked.revision, {"id": "a", "label": "The model asks", "body": "The whole thread, or only the last reply?",
                               "choices": [{"label": "The whole thread"}, {"label": "Only the last reply"}]}, "s")
    yield "ask", asked.panel()
    asked.ask(asked.revision, {"id": "p", "permission": True, "label": "Claude Code wants to run",
                               "body": "git push origin parser-fix", "code": True,
                               "choices": [{"label": "Deny"}, {"label": "Allow"}]}, "s")
    yield "permission", asked.panel()
    asked.ask(asked.revision, {"id": "r", "label": "The model says", "read": True, "body": (
        "The parser reached the end of the file while a string was still open. The quote on line 12 is never "
        "closed, so everything after it was read as part of the string."),
        "choices": [{"label": "Insert it"}, {"label": "Dismiss"}]}, "s")
    yield "answer", asked.panel()
    working = composed("fix the failing parser test")
    working.submit()
    working.note(working.revision, "Reading tests/test_parser.py")
    yield "progress", working.panel()
    working.fail(working.revision, "Connection refused")
    yield "failed", working.panel()


app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
screen = NSScreen.mainScreen().visibleFrame()
left, top = screen.origin.x + 40, screen.origin.y + screen.size.height - 40
keep = []
for index, (name, spec) in enumerate(states()):
    panel = Panel()
    column, row = index % 3, index // 3
    panel.show(((left + column * 470, top - row * 230), (2, 18)), spec)
    keep.append(panel)
overlay = Overlay()
overlay.show(((left + 470 * 2, top - 3 * 230), (2, 18)), "send the revised draft by Friday.")
keep.append(overlay)
NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
    float(sys.argv[1]) if len(sys.argv) > 1 else 30, app, "terminate:", None, False)
app.run()
