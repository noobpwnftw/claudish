"""Platform-neutral IME state. Keep compatible with PIME's Python 3.6+."""

MAX_COMPOSITION = 512
# Two modes, switched by tapping Shift as a Chinese input method switches English and pinyin.
# continue (where cd_AI starts) types like en_US: your keys go straight in, and the rest of the
# sentence waits after the caret for Tab. compose holds what you type: Tab rewrites it in place,
# Enter sends it as an instruction and offers drafts to pick, Shift+Enter keeps it as it is, and
# Esc steps back until it is gone.
MODES = ("continue", "compose")
LABELS = {"continue": "Tab continues: ", "instruct": "Enter inserts: "}
SHIFT_TAP_SECONDS = 0.5  # Shift alone, released within this: a held Shift (a click, a selection) is not a tap


class Composition:
    def __init__(self):
        self.text = ""
        self.candidate = ""
        self.candidates = []  # every reading offered; candidate is the first
        self.revision = 0
        self.mode = MODES[0]
        self.asked = None  # compose: what the pending or shown result is ("rewrite" or "instruct")
        self.working = False  # a rewrite or an instruction was asked for and its result is pending
        self.failed = False
        self.look = False  # F8 with an instruction: send a picture of the focused window too
        self.taken = False  # continue: a suggestion was just taken; wait for the next key
        self.converted = False  # compose: the rewrite shows in place of your words
        self.adopted = False  # the composition is text taken from the app (a selection): never dropped
        self.quiet = False  # the field is not prose (a URL, an email address, a number): nothing unasked
        self.question = None  # an agent session's open question: {"id", "text", "choices", "session"}
        self.reply = ""  # your own words in answer to it, typed instead of a number
        self.status = ""  # what the agent is doing, or its draft so far

    def change(self, text):
        self.reply = ""
        self.text = text
        self.candidate = ""
        self.candidates = []
        self.question, self.status = None, ""
        self.taken = False
        self.converted = False
        self.adopted = False
        self.asked = None
        self.working = self.failed = False
        if not text:
            self.look = False  # one instruction at a time; never carried to the next
        self.revision += 1

    @property
    def request_mode(self):
        """The service's mode for what is asked now: continue, rewrite, or instruct."""
        return "continue" if self.live else self.asked

    @property
    def automatic(self):
        """Ask on this pause? Only in continue, and only at a word boundary (after a space or
        punctuation), so a pause mid-word never splits it ("rev" + " iew"). A rewrite is asked
        for with Tab and an instruction with Enter: nothing is sent while you compose."""
        if self.mode == "continue" and not self.quiet:
            return bool(self.text) and not self.text[-1].isalnum() and not self.taken
        return False

    @property
    def shown(self):
        """What the composition shows: your words, or, after Tab, the rewrite in their place (like
        a CJK input method converting what you typed)."""
        if self.question and self.reply:
            return self.reply
        return self.candidate if self.converted else self.text

    def tab(self):
        """What Tab does: "pass" (the app's), "request" (ask for the rewrite; it takes your words'
        place as it arrives), "wait" (asked already), "convert" (show it in place of your words),
        or "accept" (the rewrite shown, or an instruction's first draft)."""
        if not self.text:
            return "pass"
        if self.converted or (self.asked == "instruct" and self.candidate):
            return "accept"
        if self.asked == "rewrite" and self.candidate:
            self.converted = True
            return "convert"
        if self.working:
            return "wait"
        self.asked, self.working, self.failed = "rewrite", True, False
        return "request"

    def adopt(self, text):
        """The app's selection becomes the composition (reconversion): it left the app, so Esc puts
        it back rather than dropping it."""
        self.change(text)
        self.adopted = True

    def escape(self):
        """Esc, one step back: "pass" (the app's); "clear" (a reply you were typing to an agent
        goes; its question stays); "back" (still composing: your words again instead of the
        rewrite, or your instruction again with its drafts closed and a pending answer dropped);
        "keep" (a selection taken from the app goes back as it was); or "drop" (what you typed goes,
        nothing is inserted: Shift+Enter keeps it instead)."""
        if not self.text:
            return "pass"
        if self.question and self.reply:
            self.reply = ""  # your reply goes; the question stays open
            return "clear"
        if self.converted:
            self.converted = False
            return "back"
        if self.adopted and not self.question:
            return "keep"  # text taken from the app goes back, as it was
        # Drafts showing, or an answer pending: back to your words. (A rewrite shown and dismissed
        # leaves nothing visible to step back from, so the next Esc drops.)
        if (self.candidates and self.asked == "instruct") or self.working or self.failed or self.question:
            self.change(self.text)  # a new revision: a late answer for the old one is ignored
            return "back"
        self.change("")
        return "drop"

    def enter(self):
        """What Enter does now: "pass" (the app's), "submit" (send it as an instruction), "wait",
        "accept" (the rewrite shown, or the first draft), or "reply" (an agent asked, and you typed
        your answer)."""
        if not self.text:
            return "pass"
        if self.question:
            return "reply" if self.reply.strip() else "wait"
        if self.converted or (self.asked == "instruct" and self.candidate):
            return "accept"
        return "wait" if self.working else "submit"

    def keep(self):
        """Shift+Enter: insert what you see, as it is, and keep composing; "" with nothing composed
        (then Shift+Enter is the app's, a newline in most chat boxes)."""
        if not self.text or self.live:
            return ""
        kept = self.shown if not self.question else self.text
        self.change("")
        return kept

    def submit(self):
        self.asked, self.working, self.failed = "instruct", True, False

    def fail(self, revision):
        if revision == self.revision and self.working:
            self.working, self.failed = False, True
            self.question, self.status = None, ""

    def ask(self, revision, question, session):
        """An agent asks something while working on this instruction: its choices become the list."""
        if revision != self.revision or not self.working:
            return False
        self.question = dict(question, session=session)
        self.reply = ""
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
        if not question or self.reply or not 1 <= number <= len(question.get("choices") or []):
            return None
        self.question, self.status = None, "answered: " + question["choices"][number - 1].get("label", "")
        return question["session"], question["id"], number - 1

    def passes(self, char):
        """A key that goes straight to the app instead of starting a composition: anything but a
        letter or a digit with nothing composed (the space or the punctuation after the previous
        word is not part of what you compose)."""
        return not self.live and not self.text and not char.isalnum()

    def answer_text(self):
        """(session, question id, your words) for a typed reply, or None. The agent hears it as a
        refusal carrying your words, so it can adjust ("not that repo, use the fork")."""
        question, words = self.question, self.reply.strip()
        if not question or not words:
            return None
        self.question, self.reply, self.status = None, "", "answered: " + words
        return question["session"], question["id"], words

    def insert(self, char):
        """Add a typed character; False when the adapter should commit first (the composition is
        full, or a rewrite shows in place: typing on keeps it and starts afresh)."""
        if self.question:  # typing answers the agent; the instruction it is working on stays as sent
            if len(self.reply) < MAX_COMPOSITION:
                self.reply += char
            return True
        if len(self.text) >= MAX_COMPOSITION or self.converted:
            return False
        self.change(self.text + char)  # as typed: em dashes come from the model, never from a key
        return True

    def backspace(self):
        if self.question:
            self.reply = self.reply[:-1]
            return
        if self.converted:  # back to your words, as Esc
            self.converted = False
            return
        self.change(self.text[:-1])

    def toggle(self):
        """A Shift tap, or a pick from the mode menu: switch mode. Leaving compose keeps what you
        see, as it is (Chinese input methods commit the letters you typed on Shift); returns the
        text to insert, or ""."""
        if self.live:
            self.mode = "compose"
            self.look = False
            self.change("")
            return ""
        kept = self.shown if not self.question else self.text
        self.mode = "continue"
        self.look = False
        self.change(kept[-MAX_COMPOSITION:])  # in the app now: continue's context
        return kept

    def toggle_look(self):
        """F8: attach, or stop attaching, a picture of the focused window to the instruction you are
        composing; a pending result was for the other choice, so it is dropped."""
        if self.live or not self.text:
            return False
        self.look = not self.look
        self.change(self.text)
        return True

    def offer(self, revision, text, alternatives=()):
        if revision != self.revision or not self.text:
            return False
        self.candidate = text
        self.candidates = [text] + [a for a in alternatives if a and a != text]
        if self.asked == "rewrite" and self.working:
            self.converted = True  # you asked with Tab: it takes your words' place as it arrives
        self.working = False
        self.question, self.status = None, ""
        return True

    @property
    def live(self):
        """Continue types straight into the app; the text here is only the model's context, and the
        one uncommitted thing is the suggestion (the ghost). A focus change can never commit a
        suggestion or lose your words."""
        return self.mode == "continue"

    def type_live(self, char):
        """Continue: what to commit for this key now. Exactly the key: continue types like en_US
        (hyphens in URLs and commands stay hyphens); em dashes come from the model."""
        self.change((self.text + char)[-MAX_COMPOSITION:])
        return char

    def take_ghost(self):
        """Tab in continue: the suggestion to commit, or "" (then Tab belongs to the app). Taking it
        is not a pause in your writing: nothing more is offered until you type again (asking at
        once made a model repeat its own sentence ending)."""
        ghost = self.ghost
        if ghost:
            self.change((self.text + ghost)[-MAX_COMPOSITION:])
            self.taken = True
        return ghost

    def dismiss(self):
        """Esc in continue: drop the suggestion, keep going."""
        self.candidate, self.candidates = "", []

    @property
    def ghost(self):
        """Continue: the rest of the sentence, shown greyed after the caret; Tab takes it."""
        if self.mode == "continue" and len(self.candidate) > len(self.text) and self.candidate.startswith(self.text):
            return self.candidate[len(self.text):]
        return ""

    @property
    def choosing(self):
        """A numbered list is shown: number keys pick. Only for an instruction's drafts, which you
        asked for and are waiting on, or an agent's question; while you type, digits are text."""
        return bool(self.question) or (self.asked == "instruct" and len(self.candidates) > 1)

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


class ShiftTap:
    """Shift pressed and released alone, quickly: the mode switch. Any other key while it is held
    (a capital letter, Shift+arrow) or a long hold (Shift+click) is not a tap."""

    def __init__(self):
        self.down_at = None

    def press(self, now):
        self.down_at = now

    def other(self):
        self.down_at = None

    def release(self, now):
        """True when this release ends a tap."""
        tapped = self.down_at is not None and now - self.down_at <= SHIFT_TAP_SECONDS
        self.down_at = None
        return tapped
