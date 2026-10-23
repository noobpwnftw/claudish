"""Platform-neutral IME state. Keep compatible with PIME's Python 3.6+."""

MAX_COMPOSITION = 512
# F7 cycles through these in every adapter. Switching to cd_AI starts in continue, which types like
# en_US (your keys go straight in) and only adds a suggestion you can take with Tab; one F7 asks
# for something (instruct), a second polishes your words (rewrite). Each looks different at the
# caret: continue adds after it, rewrite converts your words in place (Tab), and instruct is the
# only one with a list (its drafts).
MODES = ("continue", "instruct", "rewrite")
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
        self.taken = False  # continue: a suggestion was just taken; wait for the next key
        self.converted = False  # rewrite: Tab showed the rewrite in place of your words
        self.question = None  # an agent session's open question: {"id", "text", "choices", "session"}
        self.status = ""  # what the agent is doing, or its draft so far

    def change(self, text):
        self.text = text
        self.candidate = ""
        self.candidates = []
        self.question, self.status = None, ""
        self.taken = False
        self.converted = False
        self.working = self.failed = False
        if not text:
            self.look = False  # one instruction at a time; never carried to the next
        self.revision += 1

    @property
    def automatic(self):
        """Ask on this pause? Rewrite: always. Continue: only at a word boundary (after a space or
        punctuation), so a pause mid-word never splits it ("rev" + " iew"). Instruct: only on Enter."""
        if self.mode == "instruct":
            return False
        if self.mode == "continue":
            return bool(self.text) and not self.text[-1].isalnum() and not self.taken
        return True

    @property
    def shown(self):
        """What the composition shows: your words, or, in rewrite after Tab, the rewrite in their
        place (like a CJK input method converting what you typed)."""
        return self.candidate if self.converted else self.text

    def tab(self):
        """What Tab does: "pass" (the app's), "wait" (nothing ready yet), "convert" (rewrite: the
        result now shows in place of your words), or "accept"."""
        if not self.text:
            return "pass"
        if self.mode == "rewrite" and self.candidate and not self.converted:
            self.converted = True
            return "convert"
        return "accept" if self.candidate else "wait"

    def escape(self):
        """Esc, one step back: "pass" (the app's); "back" (still composing: your words again in
        rewrite, or the instruction again with its drafts closed and a pending answer dropped);
        "drop" (an instruction you no longer want: nothing is inserted, as it is not text you
        meant to write); or "keep" (rewrite: your words as typed)."""
        if not self.text:
            return "pass"
        if self.converted:
            self.converted = False
            return "back"
        if self.mode == "instruct":
            if self.candidates or self.working or self.failed or self.question:
                self.change(self.text)  # a new revision: a late answer for the old one is ignored
                return "back"
            self.change("")
            return "drop"
        return "keep"

    def enter(self):
        """What Enter does now: "pass", "submit", "wait", "accept" (the candidate), or "keep" (your wording)."""
        if not self.text:
            return "pass"
        if self.mode != "instruct":
            return "accept" if self.converted else "keep"
        if self.candidate:
            return "accept"
        return "wait" if self.working else "submit"

    def submit(self):
        self.working, self.failed = True, False

    def fail(self, revision):
        if revision == self.revision and self.working:
            self.working, self.failed = False, True
            self.question, self.status = None, ""

    def ask(self, revision, question, session):
        """An agent asks something while working on this instruction: its choices become the list."""
        if revision != self.revision or not self.working:
            return False
        self.question = dict(question, session=session)
        return True

    def note(self, revision, text):
        """Progress or a partial draft from the agent, for the status line."""
        if revision != self.revision or not self.working:
            return False
        self.status = text
        return True

    def answer_choice(self, number):
        """(session, question id, choice index) for the numbered choice, or None."""
        question = self.question
        if not question or not 1 <= number <= len(question.get("choices") or []):
            return None
        self.question, self.status = None, "answered: " + question["choices"][number - 1].get("label", "")
        return question["session"], question["id"], number - 1

    def insert(self, char):
        """Add a typed character; False when the adapter should commit first (the composition is
        full, or a converted rewrite: typing on keeps it and starts afresh)."""
        if len(self.text) >= MAX_COMPOSITION or self.converted:
            return False
        self.change(self.text + ("—" if char == "-" else char))
        return True

    def backspace(self):
        if self.converted:  # back to your words, as Esc
            self.converted = False
            return
        self.change(self.text[:-1])

    def next_mode(self):
        """Switch mode; the current candidate belonged to the old mode, so it is dropped."""
        leaving_live = self.live  # its words are in the app already: the next mode starts empty
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        self.look = False
        self.change("" if leaving_live else self.text)

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
        self.question, self.status = None, ""
        return True

    @property
    def live(self):
        """Continue mode types straight into the app; the text here is only the model's context,
        and the one uncommitted thing is the suggestion (the ghost). A focus change can never
        commit a suggestion or lose your words."""
        return self.mode == "continue"

    def type_live(self, char):
        """Continue mode: what to commit for this key now. Exactly the key: continue types like
        en_US (hyphens in URLs and commands stay hyphens); em dashes come from the model."""
        self.change((self.text + char)[-MAX_COMPOSITION:])
        return char

    def take_ghost(self):
        """Tab in continue mode: the suggestion to commit, or "" (then Tab belongs to the app).
        Taking it is not a pause in your writing: nothing more is offered until you type again
        (asking at once made a model repeat its own sentence ending)."""
        ghost = self.ghost
        if ghost:
            self.change((self.text + ghost)[-MAX_COMPOSITION:])
            self.taken = True
        return ghost

    def dismiss(self):
        """Esc in continue mode: drop the suggestion, keep going."""
        self.candidate, self.candidates = "", []

    @property
    def ghost(self):
        """Continue mode: the rest of the sentence, shown greyed after the caret; Tab takes it."""
        if self.mode == "continue" and len(self.candidate) > len(self.text) and self.candidate.startswith(self.text):
            return self.candidate[len(self.text):]
        return ""

    @property
    def choosing(self):
        """A numbered list is shown: number keys pick. Only for an instruction, whose result you
        asked for and are waiting on; while you type, digits are text."""
        return bool(self.question) or (self.mode == "instruct" and len(self.candidates) > 1)

    def pick(self, number):
        """Commit the numbered candidate (1-based); None if there is no such candidate."""
        if self.question or not (self.choosing and 1 <= number <= len(self.candidates)):
            return None
        text = self.candidates[number - 1]
        self.change("")
        return text

    def commit(self, suggested=False):
        """The text to insert: the candidate if asked for or already shown in place, else your words."""
        text = (self.candidate if suggested or self.converted else "") or self.text
        self.change("")
        return text
