"""Platform-neutral IME state. Keep compatible with PIME's Python 3.6+."""

MAX_COMPOSITION = 512
MODES = ("rewrite", "continue", "instruct")  # F7 cycles through these in every adapter.
LABELS = {"rewrite": "Tab: ", "continue": "Tab continues: ", "instruct": "Tab writes: "}


class Composition:
    def __init__(self):
        self.text = ""
        self.candidate = ""
        self.revision = 0
        self.mode = MODES[0]

    def change(self, text):
        self.text = text
        self.candidate = ""
        self.revision += 1

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
        return True

    def commit(self, suggested=False):
        text = (self.candidate if suggested else "") or self.text
        self.change("")
        return text
