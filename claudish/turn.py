"""One request, one answer (docs/design/architecture.md).

Every model call gets the same three things: the text box (what it is, its app, the text around
the caret, and what was observed on request), what the user did (the mode: a pause in continue,
Tab or Enter in compose, with the conversation so far), and what is available (the configured
tools). The model answers with one action: complete (continue), replace (rewrite), insert
(instruct), or ask (a question, through a tool that needs the user).

The box is described once, in the system prompt. Observations (a terminal's screen, the
profile's context, the app's bindings) go in the turn, next to the user's words, fenced as
material, not instructions: a model reads "fix" as being about what it sees there, not about
an earlier draft. A tone is for prose: a command line, a URL, or a number has none, so the
Claudish tone and its prose examples apply only to prose boxes.
"""
from .modes import TEMPLATES
from .screen import is_terminal

ACTIONS = {"continue": "complete", "rewrite": "replace", "instruct": "insert"}
WINDOW_BEFORE, WINDOW_AFTER = 1500, 500

# Free-form text needs no description of its kind. The box's words (what each kind is, what it
# means, the at-caret and tools guides) are in claudish/templates.json, "box".
PROSE = (None, "name", "alpha")
WORDS = TEMPLATES["box"]


class Box:
    """What is known about the text box this request is for."""

    def __init__(self, app=None, kind=None, before="", after=""):
        self.app = app
        self.kind = kind if kind else ("terminal" if is_terminal(app) else None)
        self.before, self.after = before or "", after or ""
        self.observations = []  # (name, text): material observed on request, fenced in the turn
        self.image = None  # a picture of the window (F8), PNG bytes
        self.consulted = []  # what was read, as the candidate window lists it

    @property
    def prose(self):
        return self.kind in PROSE

    def observe(self, name, text, consulted=None):
        if text and text.strip():
            self.observations.append((name, text.strip()))
            self.consulted.append(consulted or name)

    def clipped(self):
        """Whether the text box is longer than the window around the caret."""
        return len(self.before) > WINDOW_BEFORE or len(self.after) > WINDOW_AFTER

    def describe(self, mode, retrieval=False, words=WORDS):
        """The text box, for the system prompt: its kind and app, what the kind means, and the text
        around where the result goes (continue: the text itself is the turn, so only what follows)."""
        parts = []
        kind = words["kinds"].get(self.kind or "")
        if kind or self.app:
            parts.append("The text box is %s%s." % (kind or "a text field", " in %s" % self.app if self.app else ""))
        if self.kind in words["facts"]:
            parts.append(words["facts"][self.kind])
        before = "" if mode == "continue" else self.before
        if before or self.after:
            more = ""
            if self.clipped() and retrieval:
                more = ("\nThe text box has %d characters; this is the part around the caret, at %d. "
                        "Read or search the rest with the textbox tools."
                        % (len(self.before) + len(self.after), len(self.before)))
            head = "…" if len(before) > WINDOW_BEFORE else ""
            tail = "…" if len(self.after) > WINDOW_AFTER else ""
            parts.append("<context name=\"the text box around the caret (▮)\">\n%s%s▮%s%s\n</context>%s" % (
                head, before[-WINDOW_BEFORE:], self.after[:WINDOW_AFTER], tail, more))
            if mode == "instruct":
                parts.append(words["at_caret"])
        return "".join("\n\n" + part for part in parts)

    def material(self, said, words=WORDS):
        """The turn: what was observed, then the user's words (or the mode's frame around them)."""
        if not self.observations:
            return said
        fenced = "\n\n".join('<context name="%s">\n%s\n</context>' % (name.replace('"', "'"), text)
                             for name, text in self.observations)
        return "%s\n\n%s\n\n%s" % (words["reference"], fenced, said)

    def fit(self, mode, text):
        """The box's own constraints on what is put in it: a terminal takes one physical line (a
        newline at a prompt is a Return, which would run it without the user's Enter)."""
        if self.kind == "terminal" and mode != "continue":
            from .screen import one_line
            return one_line(text)
        return text


def observe(rewriter, box, mode, look=False, screen=None):
    """Run the observers this request calls for: the profile's context and the app's bindings, a
    terminal's screen (for compose, never for continue's pauses; screen: given instead of read),
    and a picture of the window (F8, with an instruction)."""
    for name, text in rewriter.sections(box.app):
        box.observe(name, text)
    if box.kind == "terminal" and mode != "continue" and (rewriter.read_terminal or screen):
        if screen is None:
            from .screen import read
            screen = read(box.app)
        if screen:
            box.observe("terminal screen, last lines", screen,
                        "terminal screen (%d lines)" % (screen.count("\n") + 1))
    if look:
        from .capture import capture
        box.image, width, height = capture(rewriter.look_command)
        box.consulted.append("window picture (%d×%d)" % (width, height))


def system(spec, mode, box, retrieval=False, tools=False):
    """The system prompt: the action in the tone (prose) or plain (other kinds), then the box."""
    base = spec["system"] if box.prose or spec.get("custom") else spec.get("plain", spec["system"])
    words = spec.get("box", WORDS)
    return base + box.describe(mode, retrieval, words) + ("\n\n" + words["tools"] if tools else "")
