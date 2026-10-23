"""Platform-neutral IME state. Keep compatible with PIME's Python 3.6+."""
import copy
import time

MAX_COMPOSITION = 512
# Two modes, switched by tapping Shift as a Chinese input method switches English and pinyin.
# continue (where cd_AI starts) types like en_US: your keys go straight in, and the rest of the
# sentence waits after the caret for Tab. compose holds what you type: Tab rewrites it in place,
# Enter sends it as an instruction and offers drafts to pick, Shift+Enter keeps it as it is, and
# Esc steps back until it is gone.
MODES = ("continue", "compose")
# Tab takes the model's text (a suggestion, a rewrite, a draft, an answer to read); Enter talks to the
# model (sends an instruction, a reply, an answer to its question). Enter never inserts the model's
# words, so a reflexive second Enter after sending can insert nothing (owner, 2026-10-24).
SHIFT_TAP_SECONDS = 0.5  # Shift alone, released within this: a held Shift (a click, a selection) is not a tap
# Compose's keys show when you pause this long, not while you type (docs/design/visual.md): a fluent
# typist sees only the composition; a hesitant one always sees the keys.
HINT_PAUSE_SECONDS = 0.0  # CJK reviewers: what Enter does must show from the first key (2026-10-24)
ROLLED_SHIFT_SECONDS = 0.3  # Shift pressed this soon after another key is rolled typing, not a tap
HELD_SECONDS = 600  # an exchange held after a focus change is offered on return for this long


def failure(error):
    """Why a request failed, in a few plain words for the panel."""
    error = str(error or "").lower()
    if any(word in error for word in ("refused", "unreachable", "offline", "connect", "not running")):
        return "The model is offline"
    if "timed out" in error or "timeout" in error:
        return "The model took too long"
    return "The request failed"


def split_title(text):
    """(header, body) of a question or an answer as shown: who asks or what is asked, small, then
    the rest ("The model asks: Did you mean git status?", "Send this task to claude? Fix the build")."""
    head, sep, rest = text.partition(": ")
    if sep and len(head) <= 24 and rest:
        return head, rest
    head, sep, rest = text.partition("? ")
    if sep and len(head) <= 60 and rest:
        return head + "?", rest
    return None, text


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
        self.inside = False  # text follows the caret on its line: continue waits for the end of a line
        self.question = None  # an agent session's open question: {"id", "text", "choices", "session"}
        self.reply = ""  # what you type while an instruction's exchange is open: a reply, or your next words
        self.answers = []  # your answers in this exchange, for the panel's thread ("You answered")
        self.editing = False  # the instruction came back to the caret (Esc edit): the next Esc drops it
        self.dropped = ""  # the last words Esc dropped (an instruction, or a reply): Shift+Esc brings them back
        self.dropped_reply = False
        self.nudged = None  # Enter on the model's text: what the panel showed then (see nudge)
        self.highlight = 0  # the highlighted row (↑ and ↓ move it; Tab takes a draft, Enter an answer)
        self.held = None  # a sent instruction's exchange, held when focus left the text box
        self.held_app, self.held_at = None, 0.0
        self.selected = False  # an approval has a row highlighted (↓ first): only then does Enter answer it
        self.status = ""  # what the agent is doing, or its draft so far
        self.offered_at = 0.0  # when the latest result arrived (time.monotonic)
        self.typed_at = 0.0  # when the composition last changed (time.monotonic): the hints wait for a pause
        self.error = ""  # why the last request failed, in plain words
        self.hosted = ""  # the hosted model the shown result came from ("Claude"); "" when local

    def change(self, text):
        self.reply = ""
        self.answers = []
        self.editing = False
        self.highlight = 0
        self.typed_at = time.monotonic()
        self.text = text
        self.candidate = ""
        self.candidates = []
        self.question, self.status = None, ""
        self.taken = False
        self.converted = False
        self.adopted = False
        self.asked = None
        self.working = self.failed = False
        self.error = self.hosted = ""
        if not text:
            self.look = False  # one instruction at a time; never carried to the next
        self.revision += 1

    @property
    def request_mode(self):
        """The service's mode for what is asked now: continue, rewrite, or instruct."""
        return "continue" if self.live else self.asked

    @property
    def automatic(self):
        """Ask on this pause? Only in continue, only at a word boundary (after a space or
        punctuation), so a pause mid-word never splits it ("rev" + " iew"), and only at the end of
        a line: in the middle of text a suggestion would push or cover what follows (adapters set
        inside). A rewrite is asked for with Tab and an instruction with Enter: nothing is sent
        while you compose."""
        if self.mode == "continue" and not self.quiet and not self.inside:
            return bool(self.text) and not self.text[-1].isalnum() and not self.taken
        return False

    @property
    def sent(self):
        """An instruction's exchange is open: it was sent (working, failed, asking, or offering its
        drafts). Its words have left your text: the panel shows them ("You asked")."""
        return self.asked == "instruct" and bool(self.working or self.failed or self.question or self.candidate)

    @property
    def shown(self):
        """What the composition shows, only ever what you are typing now: your words, or after Tab
        the rewrite in their place (like a CJK input method converting what you typed); once an
        instruction is sent, nothing, or what you type next (a reply)."""
        if self.sent:
            return self.reply
        return self.text  # a rewrite shows in the panel, never in your text: only Tab puts it there

    def panel(self, now=None):
        """What the panel next to the caret shows, the same for every adapter and the demo
        (docs/design/visual.md; drawn as in claudish/web/design.html), or None when nothing shows:
        {"label", "body", "code"}: the header (who asks or what this is, then the content as is);
        "rows": [{"key", "text", "legend"}] with "on" the highlighted one (-1: none, an approval);
        "foot": [(key, verb)], then "tail" (free words); "tile": "ai" or "warn"; "status" with
        "busy"; "failed" (why); "mark" (a hosted model's name). Continue shows no panel: its
        suggestion speaks for itself. Compose's keys wait for a pause (hint_due)."""
        if self.live or not (self.text or self.question):
            return None
        shown = {"thread": [], "label": None, "body": None, "code": False, "rows": [], "on": -1, "foot": [],
                 "tail": None, "tile": "ai", "status": None, "busy": False, "failed": None, "mark": None,
                 "replying": False, "take": "Enter", "nudge": False}
        question = self.question
        if self.sent:  # the exchange so far: your instruction, then your answers (the latest)
            shown["thread"] = [{"label": "You asked", "body": self.text}] + (
                [{"label": "You answered", "body": self.answers[-1]}] if self.answers else [])
        if question:
            choices = question.get("choices") or []
            label, body = question.get("label"), question.get("body")
            if body is None:
                label, body = split_title(question.get("text", ""))
            approval = bool(question.get("permission"))
            if self.reading:  # an answer to read: Tab puts it in, Esc dismisses it
                shown.update(label=label, body=body, foot=[("Tab", "insert"), ("Esc", "dismiss")],
                             tail="or type to ask more", take="Tab")
                return shown if not self.reply else dict(shown, replying=True, tail=None,
                                                          foot=[("Enter", "send reply"), ("Esc", "cancel reply")])
            shown.update(label=label, body=body, code=bool(question.get("code")),
                         on=self.highlight if self.asks or self.selected else -1,
                         rows=[{"key": "", "text": c.get("label", ""), "legend": c.get("legend") or None} for c in choices],
                         foot=[("↑↓", "choose")] + ([("Enter", "confirm")] if not approval or self.selected else []),
                         tail="or type why not" if not self.asks else "or type a reply")
        elif self.working and not self.reply:
            status = " ".join((self.status or "").split())
            shown.update(status=(status[:77] + "…" if len(status) > 80 else status)
                         or ("Rewriting" if self.asked == "rewrite" else "Working"),
                         busy=True, foot=[("Esc", "stop")])
        elif self.working:  # typing while it works: your next words, sent when you press Enter
            shown["status"], shown["busy"] = "Working", True
        elif self.failed:
            shown.update(tile="warn", failed=self.error or "The request failed", foot=[("Enter", "retry"), ("Esc", "edit")])
        elif self.choosing or (self.asked == "instruct" and self.candidate):
            readings = self.candidates or [self.candidate]
            shown.update(rows=[{"key": "", "text": c, "legend": None} for c in readings], on=self.highlight,
                         foot=([("↑↓", "choose")] if len(readings) > 1 else []) + [("Tab", "insert"), ("Esc", "edit")],
                         take="Tab", nudge=self.nudge,
                         mark=self.hosted and "from %s · hosted" % self.hosted)
        elif self.converted:  # your words stay the composition; the rewrite waits in the panel for Tab
            # Tab inserts it, as Tab inserts all the model's text; Esc dismisses it (nothing was applied).
            shown.update(label="Rewrite", body=self.candidate, foot=[("Tab", "insert"), ("Esc", "dismiss")],
                         take="Tab",
                         mark=self.hosted and "from %s · hosted" % self.hosted)
        elif self.look or self.editing or self.hint_due(now) == 0:  # after F8 or Esc: said at once
            shown["foot"] = (([("F8", "without this window")] if self.look else []) + [("Tab", "rewrite"), ("Enter", "ask")]
                             + ([("Esc", "drop")] if self.editing else [("Shift+Enter", "keep")]))
        else:
            return None
        if self.sent and self.reply:  # typing at the caret: the choices take no number; Enter sends it
            enter = ("deny with reason" if question and question.get("permission") else
                     "send reply" if question else "ask")
            shown.update(on=-1, replying=True, tail=None, foot=[("Enter", enter),
                                                                 ("Esc", "cancel reply" if question else "cancel")])
        return shown

    def toast(self):
        """The mode switch, briefly at the caret: the mode's tile, its name, and the key back (a
        panel with only a footer)."""
        compose = self.mode == "compose"
        return {"label": None, "body": None, "code": False, "rows": [], "on": -1, "tail": None,
                "tile": "ai" if compose else "cd", "status": "Compose" if compose else "Continue", "busy": False,
                "foot": [("Shift", "continue" if compose else "compose")], "failed": None, "mark": None,
                "thread": [], "replying": False}

    def dropped_toast(self):
        """After Esc discarded words: say so, briefly, with the key that brings them back."""
        return {"label": None, "body": None, "code": False, "rows": [], "on": -1, "tail": None, "tile": "ai",
                "status": "Dropped", "busy": False, "foot": [("Shift+Esc", "restore")], "failed": None,
                "mark": None, "thread": [], "replying": False, "take": "Enter", "nudge": False}

    def hint_due(self, now=None):
        """Seconds until compose's keys show (0: now), or None when they are not waiting: they show
        on a pause, so adapters redraw once then."""
        if self.live or not self.text or self.question or self.working or self.failed or self.converted \
                or self.candidate:
            return None
        waited = (time.monotonic() if now is None else now) - self.typed_at
        return max(0.0, HINT_PAUSE_SECONDS - waited)

    def hint(self, now=None):
        """The panel as one line of plain words, for a window that can only show text (IBus's
        auxiliary text where cd_AI's own panel is not drawn): "Tab rewrite · Enter ask"."""
        shown = self.panel(now)
        if not shown:
            return ""
        words = [w for w in (shown["label"] and shown["body"] and "%s: %s" % (shown["label"], shown["body"])
                             or shown["body"], shown["status"] and shown["status"] + ("…" if shown["busy"] else ""),
                             shown["failed"]) if w]
        words += ["%s %s" % key for key in shown["foot"]] + [w for w in (shown["tail"], shown["mark"]) if w]
        return " · ".join(words)

    def _showing(self):
        return (self.text, self.reply, self.highlight, self.candidate, self.converted, id(self.question))

    @property
    def nudge(self):
        """Enter was pressed on the drafts, which only Tab takes: the highlighted row lights its Tab
        key (round 5: a key that does nothing must say why; the footer's two or three keys need no
        light, owner). It lasts while the panel shows what it showed then; any key that changes it
        ends it."""
        return self.nudged is not None and self.nudged == self._showing()

    @property
    def reading(self):
        """An answer to read is offered: Tab inserts it, Esc dismisses it."""
        return bool(self.question) and bool(self.question.get("read"))

    @property
    def asks(self):
        """A question that Enter (or Tab) answers with its first choice: the model's own question or
        an answer to read. An approval (permission) is answered only with a number."""
        return bool(self.question) and not self.reply and not self.question.get("permission")

    def tab(self):
        """What Tab does: "pass" (the app's), "request" (ask for the rewrite; it takes your words'
        place as it arrives), "wait" (asked already), "convert" (show it in place of your words),
        "accept" (the rewrite shown, or an instruction's first draft), or "choose" (the first
        choice of a question that is not an approval)."""
        if not self.text:
            return "pass"
        if self.question:  # Tab inserts an answer to read; a question's choice is Enter's
            return "choose" if self.reading and not self.reply else "wait"
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
        if self.reading and not self.reply:
            return "dismiss"  # the adapter answers Dismiss; nothing is inserted
        if self.sent and self.reply:
            self.dropped, self.dropped_reply = self.reply, True  # Shift+Esc brings it back
            self.reply = ""  # what you typed goes; the exchange stays open
            return "clear"
        if self.converted:
            self.converted = False
            self.editing = True  # your words again; the next Esc drops them, and the footer says so
            return "back"
        if self.adopted and not self.question:
            return "keep"  # text taken from the app goes back, as it was
        # Drafts showing, or an answer pending: back to your words. (A rewrite shown and dismissed
        # leaves nothing visible to step back from, so the next Esc drops.)
        if (self.candidates and self.asked == "instruct") or self.working or self.failed or self.question:
            self.change(self.text)  # a new revision: a late answer for the old one is ignored
            self.editing = True  # the instruction is back at the caret; Esc again drops it
            return "back"
        self.dropped, self.dropped_reply = self.text, False
        self.change("")
        return "drop"

    def restore(self):
        """Shift+Esc with nothing composed: the instruction Esc dropped comes back to edit; "" when
        there is none (the key is the app's)."""
        if self.held is not None and not self.text and not self.live:
            held, self.held = self.held, None  # the exchange you left, back as it was
            self.__dict__.update({k: v for k, v in held.__dict__.items() if k != "held"})
            self.held = None
            return self.reply or self.text
        if self.live or not self.dropped:
            return ""
        if self.dropped_reply and self.sent and not self.reply:  # a reply you cleared, back at the caret
            self.reply, self.dropped = self.dropped, ""
            return self.reply
        if self.text:
            return ""
        self.change(self.dropped)
        self.dropped, self.editing = "", True
        return self.text

    def enter(self):
        """What Enter does now: "pass" (the app's), "submit" (send it as an instruction), "wait",
        "accept" (the rewrite shown, or the first draft), "reply" (an agent asked, and you typed
        your answer), or "choose" (the first choice of a question that is not an approval)."""
        if not self.text:
            return "pass"
        if self.question:
            if self.reply.strip():
                return "reply"
            if self.reading:
                return "wait"  # an answer to read goes in with Tab, never with Enter
            return "choose" if self.asks or self.selected else "wait"
        if self.sent and self.reply.strip():
            # Your next words, typed while it worked or with its drafts showing: a follow-up
            # instruction in the same conversation.
            self.change(self.reply.strip())
            return "submit"
        if self.asked == "instruct" and self.candidate:
            self.nudged = self._showing()
            return "wait"  # a draft goes in with Tab: its row lights Tab
        if self.converted:
            return "wait"  # the rewrite goes in with Tab, as its footer says
        if self.working:
            return "wait"
        return "submit"

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

    def fail(self, revision, error=None):
        held = self.route(revision)
        if held is not None:  # the exchange you left: it goes on, out of sight
            held.fail(revision, error)
            return
        if revision == self.revision and self.working:
            self.working, self.failed = False, True
            self.question, self.status = None, ""
            self.error = failure(error)

    def done(self, revision):
        """The instruction was carried out elsewhere (a helper took the task): nothing is inserted,
        and the instruction is finished."""
        held = self.route(revision)
        if held is not None:  # the exchange you left: it goes on, out of sight
            held.done(revision)
            return False
        if revision != self.revision or not self.working:
            return False
        self.change("")
        return True

    def ask(self, revision, question, session):
        """An agent asks something while working on this instruction: its choices become the list."""
        held = self.route(revision)
        if held is not None:  # the exchange you left: it goes on, out of sight
            held.ask(revision, question, session)
            return False
        if revision != self.revision or not self.working:
            return False
        self.question = dict(question, session=session)
        self.reply = ""
        self.highlight = 0
        self.selected = False
        return True

    def note(self, revision, text):
        """Progress or a partial draft from the agent, for the status line."""
        held = self.route(revision)
        if held is not None:  # the exchange you left: it goes on, out of sight
            held.note(revision, text)
            return False
        if revision != self.revision or not self.working:
            return False
        self.status = text
        return True

    def move(self, step):
        """↑ (-1) or ↓ (+1): move the highlight through the choices or the drafts (no wrap: two or
        three rows). An approval starts with nothing highlighted: the first ↓ lands on its safe
        choice (Deny). False when there is nothing to move (you are typing), and the key is the
        app's. Choices are not numbered: digits are text in English, as Space is."""
        if self.reply or not (self.question or (self.asked == "instruct" and len(self.candidates) > 1)):
            return False
        count = len(self.question.get("choices") or []) if self.question else len(self.candidates)
        if self.question and self.question.get("permission") and not self.selected:
            self.highlight, self.selected = 0, True
            return True
        self.highlight = max(0, min(count - 1, self.highlight + step))
        if not self.question:
            self.candidate = self.candidates[self.highlight]  # Enter and Tab take the highlighted draft
        return True

    @property
    def chosen(self):
        """The number Enter (or Tab) answers a question with: the highlighted choice."""
        return self.highlight + 1

    def answer_choice(self, number):
        """(session, question id, choice index) for the chosen choice (Enter on the highlight, or a
        click), or None."""
        question = self.question
        if not question or self.reply or not 1 <= number <= len(question.get("choices") or []):
            return None
        label = question["choices"][number - 1].get("label", "")
        self.question, self.status = None, "answered: " + label
        self.answers.append(label)
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
        self.answers.append(words)
        return question["session"], question["id"], words

    def insert(self, char):
        """Add a typed character; False when the adapter should commit first (the composition is
        full, or a rewrite shows in place: typing on keeps it and starts afresh)."""
        if self.sent:
            # The instruction has left your text: what you type now is at the caret, a reply (or
            # your next words). A Space with nothing typed does nothing (an IME user's reflex to
            # take a choice must not type into the document, nor pick).
            if char == " " and not self.reply:
                return True
            if len(self.reply) < MAX_COMPOSITION:
                self.reply += char
            return True
        if len(self.text) >= MAX_COMPOSITION:
            return False
        # A rewrite showing in the panel: typing on goes on with your words (the rewrite goes).
        self.change(self.text + char)  # as typed: em dashes come from the model, never from a key
        return True

    def backspace(self):
        if self.sent:
            self.reply = self.reply[:-1]  # nothing typed: nothing goes (the instruction is in the panel)
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

    def offer(self, revision, text, alternatives=(), hosted=""):
        """A result arrived. hosted: the hosted model that wrote it ("Claude"), said in the panel."""
        held = self.route(revision)
        if held is not None:  # the exchange you left: it goes on, out of sight
            held.offer(revision, text, alternatives, hosted)
            return False
        if revision != self.revision or not self.text:
            return False
        self.hosted = hosted or ""
        self.candidate = text
        self.candidates = [text] + [a for a in alternatives if a and a != text]
        self.highlight = 0
        self.offered_at = time.monotonic()
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
        text = (self.candidate if suggested else "") or self.text  # the model's words only when asked for
        self.change("")
        return text

    def leave(self, app=None):
        """Focus left the text box: what the app may keep. Your own words for the document go in;
        the model's words never (a rewrite is not taken); words for the model never (a reply);
        nothing is sent or approved. A sent instruction's exchange is held (its work goes on) and
        offered again on return (returned)."""
        if self.live:
            self.change("")
            return ""
        if self.sent:
            held = copy.copy(self)
            held.held = None
            self.held, self.held_app, self.held_at = held, app, time.monotonic()
            self.change("")
            return ""
        words = self.text
        self.change("")
        return words

    def returned(self, app=None):
        """Focus came back: a passive pill if an exchange is held for this app ("3 drafts ready ·
        Shift+Esc open"); it takes no keys. None otherwise; a held exchange expires."""
        held = self.held
        if held is None:
            return None
        if time.monotonic() - self.held_at > HELD_SECONDS:
            self.held = None
            return None
        if app != self.held_app or self.text:
            return None
        status = ("The model asks" if held.question else
                  "%d drafts ready" % len(held.candidates) if len(held.candidates) > 1 else
                  "A draft is ready" if held.candidate else
                  "The request failed" if held.failed else "Working on what you asked")
        return {"label": None, "body": None, "code": False, "rows": [], "on": -1, "tail": None, "tile": "ai",
                "status": status, "busy": held.working, "foot": [("Shift+Esc", "open")], "failed": None,
                "mark": None, "thread": [], "replying": False, "take": "Enter"}

    def route(self, revision):
        """A result for the held exchange (its revision): applied there, not to what is on screen."""
        return self.held if self.held is not None and revision == self.held.revision else None


class ShiftTap:
    """Shift pressed and released alone, quickly: the mode switch. Any other key while it is held
    (a capital letter, Shift+arrow), a long hold (Shift+click), or a Shift pressed right after
    another key (rolled typing, as Korean ㅃ or a fast capital) is not a tap."""

    def __init__(self):
        self.down_at = None
        self.typed_at = 0.0

    def press(self, now):
        self.down_at = None if now - self.typed_at < ROLLED_SHIFT_SECONDS else now

    def other(self):
        self.down_at = None
        self.typed_at = time.monotonic()

    def release(self, now):
        """True when this release ends a tap."""
        tapped = self.down_at is not None and now - self.down_at <= SHIFT_TAP_SECONDS
        self.down_at = None
        return tapped
