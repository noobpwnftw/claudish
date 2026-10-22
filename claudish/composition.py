"""Platform-neutral IME state. Keep compatible with PIME's Python 3.6+."""

MAX_COMPOSITION = 512
MODES = ("rewrite", "continue", "instruct")  # F7 cycles through these in every adapter.
LABELS = {"rewrite": "Tab: ", "continue": "Tab continues: ", "instruct": "Enter inserts: "}


class Composition:
    def __init__(self):
        self.text = ""
        self.candidate = ""
        self.candidates = []  # every reading offered; candidate is the first
        self.revision = 0
        self.mode = MODES[0]
        self.working = False  # An instruction was submitted and its result is pending.
        self.failed = False
        self.look = False  # F8 in instruct: send a picture of the focused window with the instruction

    def change(self, text):
        self.text = text
        self.candidate = ""
        self.candidates = []
        self.working = self.failed = False
        if not text:
            self.look = False  # one instruction at a time; never carried to the next
        self.revision += 1

    @property
    def automatic(self):
        """Rewrite and continue ask on every pause; an instruction is sent only on Enter."""
        return self.mode != "instruct"

    def enter(self):
        """What Enter does now: "pass", "submit", "wait", "accept" (the candidate), or "keep" (your wording)."""
        if not self.text:
            return "pass"
        if self.mode != "instruct":
            return "keep"
        if self.candidate:
            return "accept"
        return "wait" if self.working else "submit"

    def submit(self):
        self.working, self.failed = True, False

    def fail(self, revision):
        if revision == self.revision and self.working:
            self.working, self.failed = False, True

    def insert(self, char):
        if len(self.text) >= MAX_COMPOSITION:
            return False
        self.change(self.text + ("—" if char == "-" else char))
        return True

    def backspace(self):
        self.change(self.text[:-1])

    def next_mode(self):
        """Switch mode; the current candidate belonged to the old mode, so it is dropped."""
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        self.look = False
        self.change(self.text)

    def toggle_look(self):
        """F8: attach, or stop attaching, a picture of the focused window. Instruct only; a pending
        result was for the other choice, so it is dropped."""
        if self.mode != "instruct" or not self.text:
            return False
        self.look = not self.look
        self.change(self.text)
        return True

    def offer(self, revision, text, alternatives=()):
        if revision != self.revision or not self.text:
            return False
        self.candidate = text
        self.candidates = [text] + [a for a in alternatives if a and a != text]
        self.working = False
        return True

    @property
    def choosing(self):
        """A numbered list is shown: number keys pick. Only for an instruction, whose result you
        asked for and are waiting on; while you type, digits are text."""
        return self.mode == "instruct" and len(self.candidates) > 1

    def pick(self, number):
        """Commit the numbered candidate (1-based); None if there is no such candidate."""
        if not (self.choosing and 1 <= number <= len(self.candidates)):
            return None
        text = self.candidates[number - 1]
        self.change("")
        return text

    def commit(self, suggested=False):
        text = (self.candidate if suggested else "") or self.text
        self.change("")
        return text
