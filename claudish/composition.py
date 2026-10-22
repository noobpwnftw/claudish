"""Platform-neutral IME state. Keep compatible with PIME's Python 3.6+."""

MAX_COMPOSITION = 512
MODES = ("rewrite", "continue", "instruct")  # F7 cycles through these in every adapter.
LABELS = {"rewrite": "Tab: ", "continue": "Tab continues: ", "instruct": "Enter inserts: "}


class Composition:
    def __init__(self):
        self.text = ""
        self.candidate = ""
        self.revision = 0
        self.mode = MODES[0]
        self.working = False  # An instruction was submitted and its result is pending.
        self.failed = False

    def change(self, text):
        self.text = text
        self.candidate = ""
        self.working = self.failed = False
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
        self.change(self.text)

    def offer(self, revision, text):
        if revision != self.revision or not self.text:
            return False
        self.candidate = text
        self.working = False
        return True

    def commit(self, suggested=False):
        text = (self.candidate if suggested else "") or self.text
        self.change("")
        return text
