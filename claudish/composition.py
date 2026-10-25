"""Platform-neutral IME state. Keep compatible with PIME's Python 3.6+."""
import copy
import time

MAX_COMPOSITION = 512
# Two modes, switched by tapping Shift as a Chinese input method switches English and pinyin.
# compose (where cd_AI starts) holds what you type: Tab shows a rewrite (Tab again puts it in),
# Enter sends it as an instruction and offers drafts, Shift+Enter keeps it as it is, and Esc steps
# back until it is gone. continue types like en_US: your keys go straight in, and the rest of the
# sentence waits after the caret for Tab (docs/design/design.md).
MODES = ("compose", "continue")
# Tab takes the model's text (a suggestion, a rewrite, a draft, an answer to read); Enter talks to the
# model (sends an instruction, a reply, an answer to its question). Enter never inserts the model's
# words, so a reflexive second Enter after sending can insert nothing (owner, 2026-10-24).
SHIFT_TAP_SECONDS = 0.5  # Shift alone, released within this: a held Shift (a click, a selection) is not a tap
ROLLED_SHIFT_SECONDS = 0.3  # Shift pressed this soon after another key is rolled typing, not a tap
HELD_SECONDS = 600  # an exchange held after a focus change is offered on return for this long


def failure(error):
    """Why a request failed, in a few plain words for the panel."""
    error = str(error or "").lower()
    if "no model is set up" in error:
        return "no model is set up"
    # What a new Claude key meets first (Anthropic's own words in the error), said plainly.
    if "credit balance" in error:
        return "no credit on the Anthropic account"
    if "no claude credentials" in error:
        return "no Claude key yet"
    if "authentication" in error or "x-api-key" in error or "error code: 401" in error:
        return "Anthropic did not accept the key"
    if "http error 401" in error or "http error 403" in error:  # an OpenAI-compatible server's answer
        return "the model API did not accept the key"
    if "http error 404" in error:
        return "the model API has no such model or address"
    if any(words in error for words in ("name or service not known", "no address associated", "nodename nor servname",
                                        "getaddrinfo failed")):
        return "no such address for the model"
    if "rate limit" in error or "error code: 429" in error:
        return "too many requests"
    if "overloaded" in error or "error code: 529" in error:
        return "Anthropic is busy"
    if any(word in error for word in ("refused", "unreachable", "offline", "connect", "not running")):
        return "the model is offline"
    if "timed out" in error or "timeout" in error:
        return "the model took too long"
    return "the request failed"


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


def blank(**shown):
    """A panel description with every key a renderer reads (see Composition.panel)."""
    return dict({"thread": [], "label": None, "body": None, "code": False, "rows": [], "on": -1, "foot": [],
                 "tail": None, "tile": "ai", "status": None, "busy": False, "failed": None,
                 "replying": False, "take": "Enter", "nudge": False}, **shown)


class Composition:
    def __init__(self):
        self.text = ""
        self.candidate = ""
        self.candidates = []  # every reading offered; candidate is the first
        self.revision = 0
        self.issued = 0  # the last revision ever used: a held exchange coming back never reuses one
        self.mode = MODES[0]
        self.asked = None  # compose: what the pending or shown result is ("rewrite" or "instruct")
        self.working = False  # a rewrite or an instruction was asked for and its result is pending
        self.failed = False
        self.look = False  # F8 with an instruction: send a picture of the focused window too
        self.taken = False  # continue: a suggestion was just taken; wait for the next key
        self.converted = False  # compose: a rewrite waits in the panel for Tab (your words stay)
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
        self.error = ""  # why the last request failed, in plain words
        # The service does not answer (the adapter copies Suggestions.offline here): composing says so
        # from the first key, as cloud input methods grey out their cloud part; nothing else changes.
        self.offline = False
        # The key that sends your words to the model ("keys": {"summon"} in the config, copied here
        # by the adapter like offline); the other one puts them in as typed.
        self.summon = "Shift+Enter"

    @property
    def keeper(self):
        """The key that puts your words in as typed."""
        return "Shift+Enter" if self.summon == "Enter" else "Enter"

    def talks(self, shift):
        """Whether Enter (Shift+Enter with shift) talks to the model rather than keeping your words:
        the summon key does everything that goes to the model (an instruction, a follow-up, a reply,
        a choice), the other key only ever puts your own words in (owner, 2026-10-25)."""
        return not shift if self.summon == "Enter" else shift

    def change(self, text):
        self.reply = ""
        self.answers = []
        self.editing = False
        self.highlight = 0
        self.text = text
        self.candidate = ""
        self.candidates = []
        self.question, self.status = None, ""
        self.taken = False
        self.converted = False
        self.adopted = False
        self.asked = None
        self.working = self.failed = False
        self.error = ""
        if not text:
            self.look = False  # one instruction at a time; never carried to the next
        self.issued = max(self.issued, self.revision) + 1
        self.revision = self.issued

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
        drafts). Its words stay the composition until you type a reply."""
        return self.asked == "instruct" and bool(self.working or self.failed or self.question or self.candidate)

    @property
    def shown(self):
        """What the composition shows: your own words, never the model's (a rewrite waits in the
        panel until Tab). A sent instruction stays the composition while its exchange is open, and
        a reply you type takes its place: as in a CJK input method, choices never show without a
        composition (owner, 2026-10-24: macOS apps pass an input method Return, Tab and the arrows
        only while there is marked text, and not reliably; so on every platform)."""
        if self.sent:
            return self.reply or self.text
        return self.text

    def panel(self):
        """What the panel next to the caret shows, the same for every adapter and the demo
        (docs/design/design.md; drawn as in claudish/web/design.html), or None when nothing shows:
        "thread" (what the composition does not say: "You asked", "You answered"); "label", "body",
        "code" (the header: who asks or what this is, then the content as is); "rows":
        [{"text", "legend"}] with "on" the highlighted one (-1: none, an approval) and "take" its
        key; "foot": [(key, verb)], then "tail" (free words); "tile": "ai" or "warn"; "status" with
        "busy"; "failed" (why); "nudge" (Enter was pressed on a
        draft: its Tab lit). Continue shows no panel: its suggestion speaks for itself."""
        if self.live or not (self.text or self.question):
            return None
        shown = blank(take=self.summon)  # the key that answers a question's choice
        question = self.question
        if self.sent:
            # What the composition does not say (round 6): "You asked" only while a reply takes the
            # instruction's place at the caret; your latest answer once you answered.
            shown["thread"] = ([{"label": "You asked", "body": self.text}] if self.reply else []) + (
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
                                                          foot=[(self.summon, "send reply"), ("Esc", "cancel reply")])
            shown.update(label=label, body=body, code=bool(question.get("code")),
                         on=self.highlight if self.asks or self.selected else -1,
                         rows=[{"text": c.get("label", ""), "legend": c.get("legend") or None} for c in choices],
                         foot=[("↑↓", "choose")] + ([(self.summon, "confirm")] if not approval or self.selected else []),
                         tail="or type why not" if not self.asks else "or type a reply")
        elif self.working and not self.reply:
            status = " ".join((self.status or "").split())
            shown.update(status=(status[:77] + "…" if len(status) > 80 else status)
                         or ("rewriting" if self.asked == "rewrite" else "working"),
                         busy=True, foot=[("Esc", "stop")])
        elif self.working:  # typing while it works: your next words, sent when you press Enter
            shown["status"], shown["busy"] = "working", True
        elif self.failed:  # Tab retries a rewrite, Enter an instruction: each key asks again
            retry = "Tab" if self.asked == "rewrite" else self.summon
            shown.update(tile="warn", failed=self.error or "the request failed", foot=[(retry, "retry"), ("Esc", "edit")])
        elif self.asked == "instruct" and self.candidate:
            readings = self.candidates or [self.candidate]
            shown.update(rows=[{"text": c, "legend": None} for c in readings], on=self.highlight,
                         foot=([("↑↓", "choose")] if len(readings) > 1 else []) + [("Tab", "insert"), ("Esc", "edit")],
                         take="Tab", nudge=self.nudge)
        elif self.converted:  # your words stay the composition; the rewrite waits in the panel for Tab
            # Tab inserts it, as Tab inserts all the model's text; Esc dismisses it (nothing was applied).
            shown.update(label="Rewrite", body=self.candidate, foot=[("Tab", "insert"), ("Esc", "dismiss")],
                         take="Tab")
        elif self.offline:  # said from the first key, not found out on Tab
            shown.update(tile="warn", failed="cd_AI is offline",
                         foot=[(self.keeper, "keep")] + ([("Esc", "drop")] if self.editing else []))
        else:  # composing: the keys show from the first key (what Enter does must be known)
            shown["foot"] = (([("F8", "without this window")] if self.look else []) + [("Tab", "rewrite"), (self.summon, "ask")]
                             + ([("Esc", "drop")] if self.editing else [(self.keeper, "keep")]))
        if self.sent and self.reply:  # typing a reply at the caret: the choices fade; Enter sends it
            enter = ("deny with reason" if question and question.get("permission") else
                     "send reply" if question else "ask")
            shown.update(on=-1, replying=True, tail=None, foot=[(self.summon, enter),
                                                                 ("Esc", "cancel reply" if question else "cancel")])
        return shown

    def toast(self):
        """The mode switch, briefly at the caret: the mode's tile, its name, and the key back (a
        panel with only a footer)."""
        compose = self.mode == "compose"
        return blank(tile="ai" if compose else "cd", status="compose" if compose else "continue",
                     foot=[("Shift", "continue" if compose else "compose")])

    def dropped_toast(self):
        """After Esc discarded words: say so, briefly, with the key that brings them back."""
        return blank(status="dropped", foot=[("Shift+Esc", "restore")])

    def hint(self):
        """The panel as one line of plain words, for a window that can only show text (IBus's
        auxiliary text where cd_AI's own panel is not drawn): "Tab rewrite · Enter ask"."""
        shown = self.panel()
        if not shown:
            return ""
        words = [w for w in (shown["label"] and shown["body"] and "%s: %s" % (shown["label"], shown["body"])
                             or shown["body"], shown["status"] and shown["status"] + ("…" if shown["busy"] else ""),
                             shown["failed"]) if w]
        words += ["%s %s" % key for key in shown["foot"]] + [w for w in (shown["tail"],) if w]
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
        """A question Enter answers with its highlighted choice from the start: the model's own
        question. An approval (permission) starts with nothing highlighted: Enter answers only once
        ↓ has highlighted a choice (Deny first)."""
        return bool(self.question) and not self.reply and not self.question.get("permission")

    def tab(self):
        """What Tab does (it takes the model's text): "pass" (the app's), "request" (ask for a
        rewrite; it waits in the panel when it comes), "wait" (asked already), "convert" (a rewrite
        that came earlier: show it in the panel), "accept" (the rewrite shown, or the highlighted
        draft), or "choose" (an answer to read: insert it)."""
        if not self.text:
            return "pass"
        if self.question:  # Tab inserts an answer to read; a question's choice is Enter's
            return "choose" if self.reading and not self.reply else "wait"
        if self.reply:  # a reply you are typing: Enter sends it, and Tab takes nothing over it
            return "wait"
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
        """Shift+Esc with nothing composed: the exchange a focus change held, back as it was; else
        what Esc dropped (an instruction to edit, or a reply); "" when there is none (the key is the
        app's)."""
        if self.held is not None and not self.text and not self.live:
            held, self.held = self.held, None  # the exchange you left, back as it was
            self.__dict__.update({k: v for k, v in held.__dict__.items() if k not in ("held", "issued")})
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
        """What Enter does (it talks to the model): "pass" (the
        app's), "submit" (send it as an instruction), "reply" (send what you typed to the model's
        question), "choose" (answer with the highlighted choice), or "wait" (nothing to send: on a
        draft, the row lights Tab, the key that takes it)."""
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
            if self.asked == "instruct":
                self.nudged = ("pending", self.text, self.reply)  # a reflexive Enter: Tab lights when they come
            return "wait"
        return "submit"

    def keep(self):
        """The keeper key (Shift+Enter, or Enter when Shift+Enter summons): insert what you see, as it
        is, and keep composing; "" with nothing composed (then the key is the app's); None while an
        exchange shows and nothing is typed (the key is taken, nothing goes in)."""
        if not self.text or self.live:
            return ""
        if self.summon != "Enter" and (self.sent or self.question) and not self.reply.strip():
            # Drafts or a question showing, nothing typed: a reflexive Enter puts nothing in (your
            # instruction never lands in the app); on drafts it lights Tab, the key that takes one.
            if self.asked == "instruct" and self.candidate:
                self.nudged = self._showing()
            elif self.working:
                self.nudged = ("pending", self.text, self.reply)
            return None
        kept = self.shown  # what the composition shows (your words, or a reply)
        self.change("")
        return kept

    def submit(self):
        self.asked, self.working, self.failed = "instruct", True, False
        self.nudged = None

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
            self.candidate = self.candidates[self.highlight]  # Tab takes the highlighted draft
        return True

    def click(self, index):
        """A click on a row (0-based): it is highlighted, then taken as its key would take it:
        "choose" (answer a question with it), "accept" (insert that draft), or None."""
        rows = (self.question.get("choices") or []) if self.question else self.candidates
        if self.reply or not 0 <= index < len(rows) or not (self.question or self.asked == "instruct"):
            return None
        self.highlight, self.selected = index, True
        if self.question:
            return "choose"
        self.candidate = self.candidates[index]
        return "accept"

    def answer_choice(self, index=None):
        """(session, question id, choice index) for the highlighted choice (or `index`), or None.
        The answer joins the thread ("You answered")."""
        question = self.question
        index = self.highlight if index is None else index
        if not question or self.reply or not 0 <= index < len(question.get("choices") or []):
            return None
        label = question["choices"][index].get("label", "")
        self.question, self.status = None, ""
        self.answers.append(label)
        return question["session"], question["id"], index

    def dismissal(self):
        """Esc on an answer to read: answer it with its last choice (Dismiss), or None."""
        return self.answer_choice(len((self.question or {}).get("choices") or []) - 1)

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
        self.question, self.reply, self.status = None, "", ""
        self.answers.append(words)
        return question["session"], question["id"], words

    def insert(self, char):
        """Add a typed character; False when the adapter should commit first (the composition is
        full). Typing on past a rewrite in the panel goes on with your words; the rewrite goes."""
        if self.sent:
            # What you type now is a reply (or your next words): it takes the instruction's place
            # in the composition. A Space with nothing typed does nothing (an IME user's reflex to
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
            self.reply = self.reply[:-1]  # with nothing typed, nothing goes: the instruction stays
            return
        if self.converted:  # the rewrite goes; your words stay
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
        # A sent instruction's exchange is held, as on a focus change: back in compose, Shift+Esc
        # brings it back.
        kept = self.leave(getattr(self, "held_app", None)) if self.sent else self.shown
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
        """A result arrived."""
        held = self.route(revision)
        if held is not None:  # the exchange you left: it goes on, out of sight
            held.offer(revision, text, alternatives)
            return False
        if revision != self.revision or not self.text:
            return False
        self.candidate = text
        self.candidates = [text] + [a for a in alternatives if a and a != text]
        self.highlight = 0
        if self.asked == "rewrite" and self.working:
            self.converted = True  # you asked with Tab: it shows in the panel as it arrives
        self.working = False
        self.question, self.status = None, ""
        if self.nudged == ("pending", self.text, self.reply) and self.asked == "instruct":
            self.nudged = self._showing()  # Enter was pressed while they came, and nothing since
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

    def commit(self, suggested=False):
        """The text to insert: the candidate if asked for or already shown in place, else your words."""
        text = (self.candidate if suggested else "") or self.text  # the model's words only when asked for
        self.change("")
        return text

    def leave(self, app=None):
        """Focus left the text box: what the app may keep. Words you were still typing go in, as a
        CJK input method commits its preedit; never the model's (a rewrite is not taken). A sent
        instruction is not text for the app: it is cleared with its exchange, which is held (its work
        goes on) and offered on return (returned); Shift+Esc brings it back whole."""
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
        status = ("the model asks" if held.question else
                  "%d drafts ready" % len(held.candidates) if len(held.candidates) > 1 else
                  "a draft is ready" if held.candidate else
                  (held.error or "the request failed") if held.failed else "working on what you asked")
        return blank(status=status, busy=held.working, foot=[("Shift+Esc", "open")])

    def route(self, revision):
        """A result for the held exchange (its revision): applied there, not to what is on screen."""
        return self.held if self.held is not None and revision == self.held.revision else None


class ShiftTap:
    """Shift pressed and released alone, quickly: the mode switch. Any other key while it is held
    (a capital letter, Shift+arrow), a long hold (Shift+click), or a Shift pressed right after
    another key (rolled typing, as Korean ㅃ or a fast capital) is not a tap. Nor is Shift with Ctrl,
    Alt or Win/Cmd held (Ctrl+Shift and Alt+Shift switch keyboard layouts): chord, at press or release."""

    def __init__(self):
        self.down_at = None
        self.typed_at = 0.0

    def press(self, now, chord=False):
        self.down_at = None if chord or now - self.typed_at < ROLLED_SHIFT_SECONDS else now

    def other(self):
        self.down_at = None
        self.typed_at = time.monotonic()

    def release(self, now, chord=False):
        """True when this release ends a tap."""
        tapped = not chord and self.down_at is not None and now - self.down_at <= SHIFT_TAP_SECONDS
        self.down_at = None
        return tapped
