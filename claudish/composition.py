"""Platform-neutral IME state. Keep compatible with PIME's Python 3.6+."""
import copy
import time
import unicodedata

MAX_COMPOSITION = 512
# The text box an adapter reads and sends on each side of the caret, the same on every platform
# (Claudish's PIME reads this much too: pime.patch); the service keeps what each mode uses
# (turn.WINDOWS: an instruction 6000 before, 2000 after).
AROUND = 8000
# What a rewrite and continue send of it: (before, after); an instruction sends all of AROUND.
WINDOW = (1500, 500)


# The text boxes written in sentences (an input purpose: none, a name, letters); the others (a URL, an
# address, a number, a phone) take your words as typed, and continue suggests nothing there.
PROSE = (None, "name", "alpha")


# A dead key's accent, as it types alone, and the mark it puts on the next letter.
ACCENTS = {"`": "\u0300", "´": "\u0301", "^": "\u0302", "~": "\u0303", "¯": "\u0304", "˘": "\u0306",
           "˙": "\u0307", "¨": "\u0308", "˚": "\u030a", "˝": "\u030b", "ˇ": "\u030c", "¸": "\u0327", "˛": "\u0328"}


def accented(accent, char):
    """What a dead key's accent and the next key make: é from ´ and e; the accent alone before a
    space or the same accent; else the accent, then the character."""
    if char in (" ", accent):
        return accent
    composed = unicodedata.normalize("NFC", char + ACCENTS[accent])
    return composed if len(composed) == 1 else accent + char


def typeable(char):
    """A character a key types into the composition: printable, or a no-break space (Option+Space,
    AltGr+Space, French typing), which Python does not count as printable."""
    return bool(char) and (char.isprintable() or char in "\xa0\u202f")


def joins(char):
    """A code point that belongs to the character before it: a combining mark, a variation
    selector, a skin tone, a tag, or the joiner itself."""
    point = ord(char)
    return bool(unicodedata.combining(char)) or char in "\ufe0e\ufe0f\u200d" or 0x1F3FB <= point <= 0x1F3FF \
        or 0xE0020 <= point <= 0xE007F


def regional(char):
    return 0x1F1E6 <= ord(char) <= 0x1F1FF


def step_back(text, at):
    """Where the visible character before at starts: an emoji with its skin tone or a family joined
    by ZWJ, a flag, a letter with its accents goes as one."""
    at -= 1
    while at > 0 and (joins(text[at]) or text[at - 1] == "\u200d"):
        at -= 1
    if at > 0 and regional(text[at]) and regional(text[at - 1]):
        at -= 1
    return max(at, 0)


def step_forward(text, at):
    """Where the visible character at at ends (step_back's other direction)."""
    start, at = at, at + 1
    if at < len(text) and regional(text[start]) and regional(text[at]):
        at += 1
    while at < len(text) and (joins(text[at]) or text[at - 1] == "\u200d"):
        at += 1
    return min(at, len(text))


def window(before, after):
    """The text around the caret a rewrite sends (WINDOW)."""
    return before[-WINDOW[0]:], after[:WINDOW[1]]

# Two modes, switched by tapping Shift as a Chinese input method switches English and pinyin.
# compose (where cd_AI starts) holds what you type: Tab shows a rewrite (Tab again puts it in),
# Shift+Enter sends it as an instruction and offers drafts, Enter keeps it as it is, and Esc steps
# back until it is gone. continue types like en_US: your keys go straight in, and the rest of the
# sentence waits after the caret for Tab (docs/design/design.md).
MODES = ("compose", "continue")
# Tab takes the model's text (a suggestion, a rewrite, a draft, an answer to read); Shift+Enter talks
# to the model (sends an instruction, a follow-up, a reply, an answer to its question); Enter only puts
# your own words in. Neither inserts the model's words, so a reflexive Enter after sending inserts
# nothing (owner, 2026-10-24; Enter and Shift+Enter swapped by default, 2026-10-25).
SHIFT_TAP_SECONDS = 0.5  # Shift alone, released within this: a held Shift (a click, a selection) is not a tap
ROLLED_SHIFT_SECONDS = 0.3  # Shift pressed this soon after another key is rolled typing, not a tap
HELD_SECONDS = 600  # an exchange held after a focus change is offered on return for this long
HOLDS = 4  # text boxes with an exchange held at once (the service runs as many sessions)
# The panel stays shorter than a screen (G64): about this many rows of text at about ROW characters.
# Past it, drafts other than the highlighted one show their first two rows, and a text taller than
# the panel shows its first rows and an ellipsis. Tab still takes the whole text.
PANEL_ROWS = 24
ROW = 60


# The service's own failures, worded for the panel already (claudish/model.py, conversation.py, sessions.py,
# warm.py).
OWN_WORDS = ("the model is busy", "the answer ran past its length budget", "no answer, so the instruction stopped",
             "too many agent sessions", "the model offered nothing",
             "Claude Code ", "Codex ",  # claudish/warm.py's: busy, took longer, ended
             "Claude declined", "Claude returned no text", "the model returned no text")


def failure(error):
    """Why a request failed, in a few plain words for the panel."""
    if str(error or "").startswith(OWN_WORDS):
        return str(error)  # cd_AI's own, already said for the panel
    error = str(error or "").lower()
    if "no model is set up" in error:
        return "no model is set up"
    if "the config is not used" in error:
        return "the config has a problem: see cd_AI's settings"
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
    if "did not reach" in error:
        return "the answer did not reach cd_AI"
    return "the request failed"


# What Shift+Esc does not take back from a held exchange: where the caret is now (a field, a
# terminal) and the service's state (keys, hints, offline), besides the hold itself.
KEPT_ON_RESTORE = ("holds", "here", "issued", "summon", "hints", "offline", "terminal", "quiet",
                   "inside", "dropped", "dropped_reply", "dropped_at")

def rows_of(text):
    """About how many panel rows a text takes."""
    return sum(max(1, -(-len(line) // ROW)) for line in (text or "").split("\n"))


def shortened(text, rows):
    """The text in at most about `rows` panel rows: its first lines, cut at a word, then an ellipsis.
    Two rows or fewer read as one line (a preview)."""
    if rows_of(text) <= rows:
        return text
    if rows <= 2:
        text = " ".join(text.split())
    kept, room = [], rows * ROW
    for line in text.split("\n"):
        if len(line) >= room:
            cut = line[:room - 1].rsplit(" ", 1)[0] if " " in line[:room - 1] else line[:room - 1]
            kept.append(cut.rstrip(" ,;:—-") + "…")
            break
        kept.append(line)
        room -= max(1, -(-len(line) // ROW)) * ROW
        if room <= 0:
            kept[-1] = kept[-1].rstrip(" ,;:—-") + "…"
            break
    return "\n".join(kept)


def drafts_shown(drafts, on):
    """The drafts as their rows show them: whole while they fit the panel; past it, the highlighted
    one whole (up to the panel) and the others as two-row previews."""
    if sum(rows_of(d) for d in drafts) <= PANEL_ROWS:
        return list(drafts)
    room = max(PANEL_ROWS - 2 * (len(drafts) - 1), 6)
    return [shortened(d, room) if i == on else shortened(d, 2) for i, d in enumerate(drafts)]


def blank(**shown):
    """A panel description with every key a renderer reads (see Composition.panel)."""
    return dict({"thread": [], "label": None, "body": None, "code": False, "rows": [], "on": -1, "foot": [],
                 "tail": None, "tile": "ai", "status": None, "busy": False, "failed": None,
                 "replying": False, "nudge": False, "column": False}, **shown)


def exchange(method=None, needs="working"):
    """A result for an exchange: the held one's goes to it (it goes on, out of sight); one for an
    older revision, or once nothing is waiting (needs: working, or a continue suggestion's text), is
    stale and changes nothing. Then the method, whose True says what shows changed."""
    if method is None:
        return lambda method: exchange(method, needs)

    def routed(self, revision, *args, **kwargs):
        held = self.route(revision)
        if held is not None:
            getattr(held, method.__name__)(revision, *args, **kwargs)
            return False
        if revision != self.revision or not getattr(self, needs):
            return False
        return method(self, revision, *args, **kwargs)
    routed.__name__, routed.__doc__ = method.__name__, method.__doc__
    return routed


class Composition:
    def __init__(self):
        self.text = ""
        self.accent = ""
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
        self.quiet = False  # the field is not prose (a URL, an email address, a number): nothing unasked
        # A terminal: it may keep Esc from an input method when nothing is marked (Terminal.app), so a
        # drop says nothing there (Shift+Esc still restores where the key arrives).
        self.terminal = False
        self.inside = False  # text follows the caret on its line: continue waits for the end of a line
        self.question = None  # an agent session's open question: {"id", "text", "label", "body", "choices", "permission", "code", "read", "insert", "session"}
        self.reply = ""  # what you type while an instruction's exchange is open: a reply, or your next words
        self.back = 0  # characters after the cursor in what you type: ← → move it
        self.answers = []  # your answers in this exchange, for the panel's thread ("You answered")
        self.editing = False  # the instruction came back to the caret (Esc edit): the next Esc drops it
        self.dropped = ""  # the last words Esc dropped (an instruction, or a reply): Shift+Esc brings them back
        self.dropped_at = 0.0  # when: words dropped after a hold come back before it
        self.dropped_reply = False
        self.nudged = None  # Enter on the model's text: what the panel showed then (see nudge)
        self.highlight = 0  # the highlighted row (↑ and ↓ move it; Tab takes it: a draft or a choice)
        self.about = ""  # a follow-up's draft: the one in view (highlighted) when it was sent, not yet inserted
        # Sent instructions' exchanges, held when focus left their text box: box -> [exchange, when].
        self.holds = {}
        self.here = None  # the text box focus is in (returned), whose held exchange shows
        self.selected = False  # an approval has a row highlighted (↓ first): only then does Tab answer it
        self.status = ""  # what the agent is doing, or its draft so far
        self.error = ""  # why the last request failed, in plain words
        # The service does not answer (the adapter copies Suggestions.offline here): composing says so
        # from the first key, as cloud input methods grey out their cloud part; nothing else changes.
        # "initializing": not reached yet, just after login (the service still starting).
        self.offline = False
        # An answer you read and inserted with Tab: (session, question id, choice) for the adapter to
        # send, so the service records it (take_answering); the model is not asked again.
        self.answering = None
        # Your next words, typed while it worked, when a question came: held aside (not an answer
        # to a question you had not seen), back as the reply once you answer it.
        self.waiting = ""
        self.queued = []  # more questions the agent asked while one shows: each in turn
        # The key that sends your words to the model ("keys": {"summon"} in the config, copied here
        # by the adapter like offline); the other one puts them in as typed.
        self.summon = "Shift+Enter"
        # "hints": false in the config (copied here as summon is): no keys while you compose, no
        # mode or dropped toasts; the panel while something is pending (asked, or waiting on Tab) or
        # went wrong.
        self.hints = True

    @property
    def keeper(self):
        """The key that puts your words in as typed."""
        return "Shift+Enter" if self.summon == "Enter" else "Enter"

    def talks(self, shift):
        """Whether Enter (Shift+Enter with shift) talks to the model rather than keeping your words:
        the summon key sends every word that goes to the model (an instruction, a follow-up, a
        reply); Tab takes what it offers; the other key only ever puts your own words in, and does
        nothing once the model is asked (owner, 2026-10-25)."""
        return not shift if self.summon == "Enter" else shift

    def change(self, text):
        self.back = 0  # characters after the cursor in what you type (your words, or a reply): ← → move it
        self.accent = ""  # a dead key's accent, waiting for its letter: drawn at the cursor (drawn)
        self.reply = self.waiting = ""
        self.queued = []
        self.answers = []
        self.editing = False
        self.highlight = 0
        self.text = text
        self.candidate = ""
        self.candidates = []
        self.question, self.status = None, ""
        self.about = ""  # the draft in view: one exchange's, never the next one's
        self.taken = False
        self.converted = False
        self.asked = None
        self.working = self.failed = False
        self.error = ""
        if not text:
            self.look = False  # one instruction at a time; never carried to the next
        self.issued = max(self.issued, self.revision) + 1
        self.revision = self.issued

    @property
    def automatic(self):
        """Ask on this pause? Only in continue, only at a word boundary (after a space or
        punctuation), so a pause mid-word never splits it ("rev" + " iew"), and only at the end of
        a line: in the middle of text a suggestion would push or cover what follows (adapters set
        inside). A rewrite is asked for with Tab and an instruction with Shift+Enter: nothing is sent
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
    def for_model(self):
        """What the composition shows is for the model, not the app: a sent instruction, or a
        follow-up typed on a rewrite. A focus change never puts it in the app (leave)."""
        return self.sent or bool(self.converted and self.reply)

    @property
    def answered(self):
        """The model answered and is waiting on you: an instruction's exchange is open, or a rewrite
        shows in the panel. What you type now is about its answer (a reply, a follow-up), never more
        of your words: Esc goes back to them."""
        return self.sent or self.converted

    @property
    def shown(self):
        """What the composition shows: your own words, never the model's (a rewrite waits in the
        panel until Tab). A sent instruction stays the composition while its exchange is open, and
        a reply you type takes its place: as in a CJK input method, choices never show without a
        composition (owner, 2026-10-24: macOS apps pass an input method Return, Tab and the arrows
        only while there is marked text, and not reliably; so on every platform)."""
        if self.answered:
            return self.reply or self.text
        return self.text

    @property
    def drawn(self):
        """What the composition draws: what it shows, and a dead key's accent waiting at the cursor
        for its letter, as the OS's own input draws it (never committed)."""
        at = self.cursor
        return self.shown[:at] + self.accent + self.shown[at:]

    @property
    def drawn_cursor(self):
        return self.cursor + len(self.accent)

    @property
    def cursor(self):
        """Where the cursor is in what the composition shows (← and → move it; at its end by default)."""
        return len(self.shown) - (self.back if (self.reply or not self.answered) else 0)

    def arrow(self, step):
        """← (-1), → (1), Home ("home") or End ("end") in what you are typing, as a CJK input method
        moves in its composition:
        True when it is ours (nothing commits); False with nothing composed (the key is the app's).
        While an exchange is open with nothing typed, the key does nothing: it never leaves it."""
        typed = self.reply if self.answered else self.text
        if self.answered and not typed:
            return True
        if not typed or self.live:
            return False
        if step in ("home", "end"):  # Home and End: to the start or the end of it
            self.back = len(typed) if step == "home" else 0
            return True
        at = len(typed) - self.back
        if step < 0 and at > 0:
            at = step_back(typed, at)
        elif step > 0 and at < len(typed):
            at = step_forward(typed, at)
        self.back = len(typed) - at
        return True

    def delete(self):
        """Delete: the character after the cursor; True when it is ours (False: nothing composed)."""
        typed = self.reply if self.answered else self.text
        if self.answered and not typed:
            return True  # an answer waits: nothing to delete, and the key never leaves it
        if not typed or self.live:
            return False
        if self.back:
            at = len(typed) - self.back
            end = step_forward(typed, at)
            if self.answered:
                self.reply = typed[:at] + typed[end:]
                self.back -= end - at
            else:
                self.edit(typed[:at] + typed[end:], self.back - (end - at))
        return True

    def edit(self, text, back):
        """Your words changed at the cursor: a new composition, the cursor kept where it was."""
        self.change(text)
        self.back = back

    def panel(self):
        """What the panel next to the caret shows, the same for every adapter and the demo
        (docs/design/design.md; drawn as in claudish/web/design.html), or None when nothing shows:
        "thread" (what the composition does not say: "You asked", "You answered"); "label", "body",
        "code" (the header: who asks or what this is, then the content as is); "rows":
        [{"text", "legend"}] with "on" the highlighted one (-1: none, an approval), Tab taking it;
        "column" (the rows keep the key's column from the start); "foot": [(key, verb)], then "tail"
        (free words); "replying" (you are typing a reply: the choices fade); "tile": "ai", "warn", or
        "cd" (continue's toast); "status" with "busy"; "failed" (why); "nudge" (a key that does
        nothing here lit the Tab of the highlighted draft or choice). Continue shows no panel: its
        suggestion speaks for itself."""
        if self.live or not (self.text or self.question):
            return None
        if not (self.hints or self.waits_on_you()):
            return None
        shown = blank()
        question = self.question
        if self.sent:
            # What the composition does not say (round 6): "You asked" only while a reply takes the
            # instruction's place at the caret; your latest answer once you answered.
            shown["thread"] = ([{"label": "You asked", "body": self.text}] if self.reply else []) + (
                [{"label": "You answered", "body": self.answers[-1]}] if self.answers else []) + (
                [{"label": "Waiting", "body": self.waiting}] if self.waiting else [])
        if question:
            choices = question.get("choices") or []
            label, body = question.get("label"), question.get("body")
            if body is None:  # every driver sends a body; the text alone, if one does not
                body = question.get("text", "")
            approval = bool(question.get("permission"))
            if self.reading:  # an answer to read: Tab puts it in, Esc dismisses it
                shown.update(label=label, body=shortened(body, PANEL_ROWS), foot=[("Tab", "insert"), ("Esc", "dismiss")],
                             tail="or type to ask more")
                return shown if not self.reply else dict(shown, replying=True, tail=None,
                                                          foot=[(self.summon, "send reply"), ("Esc", "cancel reply")])
            shown.update(label=label, body=body, code=bool(question.get("code")),
                         on=self.highlight if self.asks or self.selected else -1,
                         rows=[{"text": c.get("label", ""), "legend": c.get("legend") or None} for c in choices],
                         # The take column and the footer from the start, so ↓ does not resize the panel.
                         foot=[("↑↓", "choose"), ("Tab", "confirm")], column=bool(choices),
                         tail="or type why not" if not self.asks else "or type a reply", nudge=self.nudge)
        elif self.working and not self.reply:
            status = " ".join((self.status or "").split())
            shown.update(status=(status[:77] + "…" if len(status) > 80 else status)
                         or ("rewriting" if self.asked == "rewrite" else "working"),
                         busy=True, foot=[("Esc", "stop")])
        elif self.working:  # typing while it works: your next words, sent with Shift+Enter
            shown["status"], shown["busy"] = "working", True
        elif self.failed:  # Tab retries a rewrite, Shift+Enter an instruction: each key asks again
            retry = "Tab" if self.asked == "rewrite" else self.summon
            kept = [(self.keeper, "keep")] if self.asked == "rewrite" else []  # your words; an instruction is not
            shown.update(tile="warn", failed=self.error, foot=[(retry, "retry")] + kept + [("Esc", "edit")])
        elif self.asked == "instruct" and self.candidate:
            readings = self.candidates
            shown.update(rows=[{"text": c, "legend": None} for c in drafts_shown(readings, self.highlight)], on=self.highlight,
                         foot=([("↑↓", "choose")] if len(readings) > 1 else []) + [("Tab", "insert"), ("Esc", "edit")],
                         tail="or type to change it", nudge=self.nudge)  # a follow-up about the highlighted one
        elif self.converted:  # your words stay the composition; the rewrite waits in the panel for Tab
            # Tab inserts it, as Tab inserts all the model's text; Esc dismisses it (nothing was applied);
            # what you type is a follow-up about it.
            shown.update(label="Rewrite", body=shortened(self.candidate, PANEL_ROWS), foot=[("Tab", "insert"), ("Esc", "dismiss")],
                         tail="or type to change it")
        elif self.offline:  # said from the first key, not found out on Tab
            shown.update(tile="warn", failed="cd_AI is initializing" if self.offline == "initializing" else "cd_AI is offline",
                         foot=[(self.keeper, "keep")] + ([("Esc", "drop")] if self.editing else []))
        else:  # composing: the keys show from the first key (what each Enter does must be known)
            shown["foot"] = (([("F8", "without this window")] if self.look else []) + [("Tab", "rewrite"), (self.summon, "ask")]
                             + [(self.keeper, "keep")] + ([("Esc", "drop")] if self.editing else []))
        if self.answered and self.reply:  # typing a reply at the caret: the choices fade; Shift+Enter sends it
            enter = ("deny with reason" if question and question.get("permission") else
                     "send reply" if question else "ask")
            # Drafts keep the highlight: a follow-up is about the draft in view (Composition.about);
            # Tab takes nothing while you type, so the row shows no key.
            shown.update(on=self.highlight if shown["rows"] and not question else -1, replying=True, tail=None, foot=[(self.summon, enter),
                                                                 ("Esc", "cancel reply" if question else "cancel")])
        return shown

    @staticmethod
    def selectable(text):
        """A selection Tab can take as your words: one line you could have typed (at most
        MAX_COMPOSITION characters, not blank). A longer or multi-line one is not a composition:
        Tab is the app's."""
        lines = (text or "").splitlines()
        return len(lines) == 1 and lines[0] == text and bool(text.strip()) and len(text) <= MAX_COMPOSITION

    def field(self, purpose=None, terminal=False):
        """Where the caret is, as the adapter knows it: a field's purpose (url, email, number...) and
        whether it is a terminal. Neither is prose: nothing is asked unasked."""
        self.terminal = terminal
        self.quiet = purpose not in PROSE or terminal

    def waits_on_you(self):
        """Something is pending or went wrong: the model works on what you asked, what it offers
        waits for your Tab (a question or an answer to read, drafts, a rewrite), a request failed,
        or cd_AI is offline."""
        return bool(self.working or self.question or self.converted or self.failed or self.offline
                    or (self.asked == "instruct" and self.candidate))

    def toast(self):
        """The mode switch, briefly at the caret: the mode's tile, its name, and the key back (a
        panel with only a footer). None with hints off."""
        if not self.hints:
            return None
        compose = self.mode == "compose"
        return blank(tile="ai" if compose else "cd", status="compose" if compose else "continue",
                     foot=[("Shift", "continue" if compose else "compose")])

    def dropped_toast(self):
        """After Esc discarded words: say so, briefly, with the key that brings them back (None with
        hints off, in a terminal, or when a reply was cleared: the question's panel stays and says
        what is left)."""
        if not self.hints or self.terminal or self.answered:
            return None
        return blank(status="dropped", foot=[("Shift+Esc", "restore")])

    def done_toast(self, said):
        """A helper took the task ("opened in a new window"): said briefly at the caret (None with
        hints off)."""
        return blank(status=said) if self.hints and said else None

    def hint(self):
        """The panel as one line of plain words, for a window that can only show text (IBus's
        auxiliary text where cd_AI's own panel is not drawn): "Tab rewrite · Shift+Enter ask"."""
        shown = self.panel()
        if not shown:
            return ""
        words = [w for w in (shown["label"] and shown["body"] and "%s: %s" % (shown["label"], shown["body"])
                             or shown["body"], shown["status"] and shown["status"] + ("…" if shown["busy"] else ""),
                             shown["failed"]) if w]
        words += ["%s %s" % key for key in shown["foot"]] + [w for w in (shown["tail"],) if w]
        return " · ".join(words)

    def light_tab(self):
        """A key that does nothing here: the highlighted row Tab would take lights its Tab (a draft,
        or a question's highlighted choice); True when one did. An approval with nothing highlighted
        lights nothing: no choice is offered to a reflexive key (owner: as drafts do, 2026-10-25)."""
        if self.reply.strip():
            return False
        if (self.question and (self.asks or self.selected) and not self.reading) or \
                (not self.question and self.asked == "instruct" and self.candidate):
            self.nudged = self._showing()
            return True
        return False

    def _showing(self):
        return (self.text, self.reply, self.highlight, self.candidate, id(self.question))

    def _pending(self):
        """A nudge given while the drafts were on their way: Tab lights when they come."""
        return ("pending", self.text, self.reply)

    @property
    def nudge(self):
        """A key that does nothing here (the summon or keeper key) was pressed on a draft or a
        question's highlighted choice, which only Tab takes: the highlighted row lights its Tab
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
        """A question Tab answers with its highlighted choice from the start: the model's own
        question. An approval (permission) starts with nothing highlighted: Tab answers only once
        ↓ has highlighted a choice (Deny first)."""
        return bool(self.question) and not self.reply and not self.question.get("permission")

    def tab(self):
        """What Tab does (it takes the model's text): "pass" (the app's), "request" (ask for a
        rewrite; it waits in the panel when it comes), "wait" (asked already), "convert" (a rewrite
        that came earlier: show it in the panel), "accept" (the rewrite shown, or the highlighted
        draft, or an answer to read: inserted, and recorded with take_answering), or "choose" (a
        question's highlighted choice, Allow or Deny included). Tab takes everything the model
        offers; the summon key only sends words."""
        if not self.text:
            return "pass"
        if self.question and self.reading and not self.reply:
            # What you read goes in now, as shown (a terminal's one line); "Insert it" goes back to
            # the service to be recorded, and no second answer is waited for.
            insert = self.question.get("insert") or self.question.get("body") or ""
            self.answering = self.answer_choice(0)
            self.candidate = insert
            return "accept"
        if self.question:  # the highlighted choice (an approval: ↓ first)
            return "choose" if not self.reply and (self.asks or self.selected) else "wait"
        if self.reply:  # a reply you are typing: Shift+Enter sends it, and Tab takes nothing over it
            return "wait"
        if self.converted or (self.asked == "instruct" and self.candidate):
            return "accept"
        if self.asked == "rewrite" and self.candidate:
            self.converted = True
            return "convert"
        if self.working or (self.failed and self.asked == "instruct"):
            return "wait"  # a failed instruction is retried with the summon key, as its footer says
        self.asked, self.working, self.failed = "rewrite", True, False
        return "request"

    def escape(self):
        """Esc, one step back: "pass" (the app's); "clear" (a reply you were typing to an agent
        goes; its question stays); "back" (still composing: your words again instead of the
        rewrite, or your instruction again with its drafts closed and a pending answer dropped);
        "dismiss" (an answer to read is answered Dismiss, nothing inserted); or "drop" (what you
        typed goes, nothing is inserted: the keeper key keeps it instead)."""
        if not self.text:
            return "pass"
        if self.reading and not self.reply:
            return "dismiss"  # the adapter answers Dismiss; nothing is inserted
        if self.answered and self.reply:
            self.dropped, self.dropped_reply, self.dropped_at = self.reply, True, time.monotonic()  # Shift+Esc brings it back
            self.reply = ""  # what you typed goes; the exchange stays open
            self.back = 0
            return "clear"
        if self.converted:
            # Your words again, the rewrite forgotten: Tab asks for another take. The next Esc drops
            # them, and the footer says so.
            self.converted, self.candidate, self.candidates = False, "", []
            self.editing = True
            return "back"
        # Drafts showing, or an answer pending: back to your words. (A rewrite shown and dismissed
        # leaves nothing visible to step back from, so the next Esc drops.)
        if (self.candidates and self.asked == "instruct") or self.working or self.failed or self.question:
            self.change(self.text)  # a new revision: a late answer for the old one is ignored
            self.editing = True  # the instruction is back at the caret; Esc again drops it
            return "back"
        self.dropped, self.dropped_reply, self.dropped_at = self.text, False, time.monotonic()
        self.change("")
        return "drop"

    def restore(self):
        """Shift+Esc with nothing composed: the exchange a focus change held, back as it was; else
        what Esc dropped (an instruction to edit, or a reply); "" when there is none (the key is the
        app's)."""
        self.expire()
        newer = self.dropped and self.dropped_at > self.held_at  # what the toast just offered (here)
        if self.held is not None and not self.text and not self.live and not newer:
            held, self.held = self.held, None  # the exchange you left, back as it was
            # The exchange comes back; this field and the service's state stay as they are now.
            self.__dict__.update({k: v for k, v in held.__dict__.items() if k not in KEPT_ON_RESTORE})
            return self.reply or self.text
        if self.live or not self.dropped:
            return ""
        if self.dropped_reply and self.answered and not self.reply:  # a reply you cleared, back at the caret
            self.reply, self.dropped = self.dropped, ""
            self.back = 0
            return self.reply
        if self.text:
            return ""
        self.change(self.dropped)
        self.dropped, self.editing = "", True
        return self.text

    def enter(self):
        """What the summon key does (Shift+Enter; it talks to the model): "pass" (the
        app's), "submit" (send it as an instruction), "reply" (send what you typed to the model's
        question), or "wait" (nothing to send: a choice is Tab's; on a draft, the row lights Tab)."""
        if not self.text:
            return "pass"
        if self.question:
            if self.reply.strip():
                return "reply"
            self.light_tab()
            return "wait"  # a choice, or an answer to read, is Tab's: the highlighted row lights Tab
        if self.answered and self.reply.strip():
            # Your next words, typed while it worked or with its drafts showing: a follow-up
            # instruction in the same conversation, about the draft in view (not in the text yet).
            drafts = self.candidates or ([self.candidate] if self.candidate else [])
            about = drafts[self.highlight] if 0 <= self.highlight < len(drafts) else ""
            # Before any answer, the first instruction goes with it: the new one replaces its
            # session, which the conversation does not keep, and the model would have only this.
            first = self.text.strip() if self.sent and not (drafts or self.converted) else ""
            self.change(" ".join(part for part in (first, self.reply.strip()) if part))  # one line, as typed
            self.about = about
            return "submit"
        if self.asked == "instruct" and self.candidate:
            self.light_tab()
            return "wait"  # a draft goes in with Tab: its row lights Tab
        if self.converted:
            return "wait"  # the rewrite goes in with Tab, as its footer says
        if self.working:
            if self.asked == "instruct":
                self.nudged = self._pending()  # a reflexive Enter: Tab lights when they come
            return "wait"
        if not (self.failed and self.asked == "instruct"):  # a retry of a failed follow-up keeps its draft
            self.about = ""
        return "submit"

    def keep(self):
        """The keeper key (Enter, or Shift+Enter when Enter summons): insert what you see, as it
        is, and keep composing; "" with nothing composed (then the key is the app's); None once the
        model is asked, a rewrite included (the key is taken, nothing goes in)."""
        if not self.text or self.live:
            return ""
        if self.sent or self.question or self.working or self.converted:  # a failed rewrite leaves only your words
            # Once the model is summoned the key is gated (owner): your instruction or a reply never
            # lands in the app by a reflexive press; the row Tab would take lights its Tab.
            if not self.light_tab() and self.working and self.asked == "instruct" and not self.question:
                self.nudged = self._pending()
            return None
        kept = self.shown  # what the composition shows (your words, or a reply)
        self.change("")
        return kept

    def submit(self):
        self.back = 0  # your next words, a reply, start at the end
        self.asked, self.working, self.failed = "instruct", True, False
        self.converted, self.candidate, self.candidates = False, "", []  # a rewrite earlier is not this answer
        self.nudged = None

    def follow(self, worker):
        """The worker's view of the service, copied each poll: the config's keys and hints, and
        whether it answers. True when that changed (offline or back)."""
        self.summon, self.hints = worker.summon, worker.hints
        # What the worker's agent sessions are for: the exchange on screen and the held ones.
        self.expire()
        worker.wanted = {self.revision} | {held.revision for held, _ in self.holds.values()}
        changed, self.offline = self.offline != worker.offline, worker.offline
        return changed

    def receive(self, revision, data):
        """A result from the worker: a draft, a question, progress, done elsewhere, or an error.
        Returns its kind ("text", "question", "progress", "done", "error") when it changed what
        shows, else None; the adapter draws it its own way."""
        if "text" in data:
            return "text" if self.offer(revision, data["text"], data.get("candidates", ())) else None
        if "question" in data:
            return "question" if self.ask(revision, data["question"], data["session"]) else None
        if "progress" in data or "partial" in data:
            return "progress" if self.note(revision, data.get("progress") or data.get("partial")) else None
        if "done" in data:
            return "done" if self.done(revision) else None
        if "error" in data:
            # The panel says why: Tab retries a rewrite, the summon key an instruction.
            return "error" if self.fail(revision, data["error"]) else None
        return None

    @exchange
    def fail(self, revision, error=None):
        """The request failed; True when that changed what shows."""
        self.working, self.failed = False, True
        self.question, self.status, self.queued = None, "", []  # a retry starts with no questions of this one
        # Words set aside while a question was up come back to edit, as when it is answered.
        self.reply, self.waiting = (self.reply + " " + self.waiting).strip(), ""
        self.error = failure(error)
        return True

    @exchange
    def done(self, revision):
        """The instruction was carried out elsewhere (a helper took the task): nothing is inserted,
        and the instruction is finished."""
        # Words you typed meanwhile stay at the caret, a composition of their own (Shift+Enter
        # sends them as the next instruction in this conversation).
        self.change((self.reply.strip() + " " + self.waiting).strip() if self.waiting else self.reply.strip())
        return True

    @exchange
    def ask(self, revision, question, session):
        """An agent asks something while working on this instruction: its choices become the list."""
        if self.question and self.question.get("id") != question.get("id"):
            self.queued.append(dict(question, session=session))  # one at a time: it shows once this one is answered
            return True
        self.question = dict(question, session=session)
        if self.reply.strip():  # your next words wait aside: they were not an answer to this
            self.waiting = (self.waiting + " " + self.reply.strip()).strip()
        self.reply = ""
        self.back = 0
        self.highlight = 0
        self.selected = False
        return True

    @exchange
    def note(self, revision, text):
        """Progress or a partial draft from the agent, for the status line."""
        self.status = text
        return True

    def move(self, step):
        """↑ (-1) or ↓ (+1): move the highlight through the choices or the drafts (no wrap: two or
        three rows). An approval starts with nothing highlighted: the first ↓ lands on its safe
        choice (Deny). A single draft takes the key too, moving nothing: passed on, it ended the
        exchange. False when there is nothing to choose from (you are typing), and the key is the
        app's. Choices are not numbered: digits are text in English, as Space is."""
        if self.reply or not (self.question or (self.asked == "instruct" and self.candidate)):
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

    def next_question(self):
        """After an answer: the next queued question shows, or your waiting words come back."""
        if self.queued:
            self.question = self.queued.pop(0)
            self.highlight, self.selected = 0, False
        else:
            self.reply, self.waiting = self.waiting, ""  # your next words, back at the caret

    def take_answering(self):
        """The answer to send for an answer to read you inserted (see answering), once."""
        answering, self.answering = self.answering, None
        return answering

    def answer_choice(self, index=None):
        """(session, question id, choice index) for the highlighted choice (or `index`), or None.
        The answer joins the thread ("You answered")."""
        question = self.question
        index = self.highlight if index is None else index
        if not question or self.reply or not 0 <= index < len(question.get("choices") or []):
            return None
        label = question["choices"][index].get("label", "")
        self.question, self.status = None, ""
        self.next_question()
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
        self.question, self.status = None, ""
        self.reply = ""
        self.back = 0
        self.next_question()
        self.answers.append(words)
        return question["session"], question["id"], words

    def insert(self, char):
        """Add a typed character; False when the adapter should commit first (the composition is
        full). With an answer waiting (a rewrite in the panel too), it is a reply or a follow-up."""
        if self.answered:
            # What you type now is a reply (or your next words): it takes the instruction's place
            # in the composition. A Space with nothing typed does nothing (an IME user's reflex to
            # take a choice must not type into the document, nor pick).
            if char == " " and not self.reply:
                return True
            if not self.reply:
                self.back = 0  # a reply starts at its end, wherever the cursor was in your words
            if len(self.reply) < MAX_COMPOSITION:
                at = len(self.reply) - self.back
                self.reply = self.reply[:at] + char + self.reply[at:]
            return True
        if len(self.text) >= MAX_COMPOSITION:
            return False
        # A rewrite showing in the panel: typing on goes on with your words (the rewrite goes).
        at = len(self.text) - self.back  # as typed: em dashes come from the model, never from a key
        self.edit(self.text[:at] + char + self.text[at:], self.back)
        return True

    def make_room(self):
        """The composition is full (insert said False): what is before the cursor goes in (returned,
        for the adapter to commit), and the rest stays your composition, the cursor at its start,
        so the next key lands where you are."""
        at = len(self.text) - self.back
        head, tail = (self.text[:at], self.text[at:]) if at else (self.text, "")
        self.edit(tail, len(tail))
        return head

    def backspace(self):
        if self.answered and (self.reply or self.sent):  # with nothing typed, nothing goes: the instruction stays
            at = len(self.reply) - self.back
            if at > 0:
                self.reply = self.reply[:step_back(self.reply, at)] + self.reply[at:]
            return
        if self.converted:  # the rewrite is hidden; your words stay, and Tab shows it again
            self.converted = False
            return
        at = len(self.text) - self.back
        if at > 0:
            self.edit(self.text[:step_back(self.text, at)] + self.text[at:], self.back)

    def toggle(self):
        """A Shift tap, or a pick from the mode menu: switch mode. Leaving compose keeps what you
        see, as it is (Chinese input methods commit the letters you typed on Shift); returns the
        text to insert, or ""."""
        if self.live:
            self.mode = "compose"
            self.change("")
            return ""
        # An exchange (a sent instruction, a follow-up on a rewrite) is held, as on a focus change:
        # back in compose its pill says what waits (switched()), and Shift+Esc brings it back.
        kept = self.leave(None) if self.for_model else self.text  # held, as on a focus change
        self.mode = "continue"
        self.look = False  # change() keeps it with words in the composition
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

    @exchange(needs="text")
    def offer(self, revision, text, alternatives=()):
        """A result arrived."""
        if self.asked == "rewrite":  # it takes your words' place: the spaces around them stay
            lead = self.text[:len(self.text) - len(self.text.lstrip())]
            trail = self.text[len(self.text.rstrip()):]
            text, alternatives = (lead + text.strip() + trail,
                                  [lead + a.strip() + trail for a in alternatives if a and a.strip()])
        self.candidate = text
        self.candidates = [text] + [a for a in alternatives if a and a != text]
        self.highlight = 0
        if self.asked == "rewrite" and self.working:
            self.converted = True  # you asked with Tab: it shows in the panel as it arrives
        self.working = False
        self.question, self.status = None, ""
        if self.nudged == self._pending() and self.asked == "instruct":
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
        """Esc in continue: drop the suggestion, keep going; nothing more is offered until you type
        again (asked at once, the same suggestion came back on Windows and macOS)."""
        self.candidate, self.candidates = "", []
        self.taken = True

    @property
    def ghost(self):
        """Continue: the rest of the sentence, shown greyed after the caret; Tab takes it."""
        if self.mode == "continue" and len(self.candidate) > len(self.text) and self.candidate.startswith(self.text):
            return self.candidate[len(self.text):]
        return ""

    def commit(self, suggested=False):
        """The text to insert: the candidate if asked for or shown in the panel, else your words."""
        text = (self.candidate if suggested else "") or self.text  # the model's words only when asked for
        # Your next words, back as the reply (an answer to read taken with Tab while they waited),
        # stay at the caret as a composition of their own.
        self.change(self.reply.strip() if suggested else "")
        return text

    def leave(self, app=None):
        """Focus left the text box: what the app may keep. Words you were still typing go in, as a
        CJK input method commits its preedit; never the model's (a rewrite is not taken). A sent
        instruction, or a follow-up typed on a rewrite, is not text for the app: it is cleared with its
        exchange, which is held (its work goes on) and offered on return (returned); Shift+Esc brings
        it back whole, with what you were typing."""
        if self.live:
            self.change("")
            return ""
        if self.for_model:  # a sent instruction, or a follow-up typed on a rewrite: held, as it is
            held = copy.copy(self)
            held.holds = {}
            box = self.here if app is None else app  # a Shift tap: held for the box you are in
            self.holds.pop(box, None)
            while len(self.holds) >= HOLDS:  # the oldest goes (its agent session with it)
                del self.holds[min(self.holds, key=lambda each: self.holds[each][1])]
            self.holds[box] = [held, time.monotonic()]
            self.change("")
            return ""
        words = self.text
        self.change("")
        return words

    def returned(self, app=None):
        """Focus came back: a passive pill if an exchange is held for this app ("3 drafts ready ·
        Shift+Esc open"); it takes no keys. None otherwise; a held exchange expires."""
        self.here = app  # its held exchange, if any, is the one the pill and Shift+Esc are about
        return self.held_pill() if self.held is not None else None

    def switched(self):
        """What a mode switch shows: back in compose with an exchange held (a Shift tap left it),
        its pill, until your next key; else the mode's toast. (spec or None, lasting)."""
        pill = self.held_pill() if self.mode == "compose" else None
        return (pill, True) if pill else (self.toast(), False)

    def caret_after(self, after):
        """The text after the caret, read at each key in continue: whether the caret is inside a
        line (continue waits for its end), and what continue sends of it."""
        self.inside = bool(after.split("\n", 1)[0].strip())
        return after[:WINDOW[1]]

    def restorable(self):
        """Whether Shift+Esc has something to bring back (a held exchange past HELD_SECONDS has none)."""
        self.expire()
        return self.held is not None or bool(self.dropped)

    @property
    def held(self):
        """The exchange held for the text box you are in, or None."""
        return self.holds.get(self.here, (None,))[0]

    @held.setter
    def held(self, exchange):
        if exchange is None:
            self.holds.pop(self.here, None)
        else:
            self.holds[self.here] = [exchange, time.monotonic()]

    @property
    def held_at(self):
        return self.holds.get(self.here, (None, 0.0))[1]

    @held_at.setter
    def held_at(self, when):
        if self.here in self.holds:
            self.holds[self.here][1] = when

    def expire(self):
        """Held exchanges older than HELD_SECONDS go (their agent sessions with them); True if this
        box's went."""
        gone = False
        for box, (_, when) in list(self.holds.items()):
            if time.monotonic() - when > HELD_SECONDS:
                del self.holds[box]
                gone = gone or box == self.here
        return gone

    def held_pill(self):
        """The held exchange's pill, or None (in continue Shift+Esc cannot open it; your words come first)."""
        held = self.held
        if held is None or self.live or self.text or self.expire():
            return None
        status = ("the model asks" if held.question else
                  "a rewrite is ready" if held.converted else
                  "%d drafts ready" % len(held.candidates) if len(held.candidates) > 1 else
                  "a draft is ready" if held.candidate else
                  held.error if held.failed else "working on what you asked")
        return blank(status=status, busy=held.working, foot=[("Shift+Esc", "open")])

    def route(self, revision):
        """A result for a held exchange (its revision): applied there, not to what is on screen."""
        return next((held for held, _ in self.holds.values() if held.revision == revision), None)


class ShiftTap:
    """Shift pressed and released alone, quickly: the mode switch. Any other key while it is held
    (a capital letter, Shift+arrow), a long hold (Shift+click), or a Shift pressed right after
    another key (rolled typing, as Korean ㅃ or a fast capital) is not a tap. Nor is Shift with Ctrl,
    Alt or Win/Cmd held (Ctrl+Shift and Alt+Shift switch keyboard layouts): chord, at press or release."""

    def __init__(self):
        self.down_at = None
        self.typed_at = 0.0
        # Pressed, and no other key since: another press is the key's auto-repeat (Windows repeats
        # the last key pressed, Shift included), not a new press.
        self.down = False

    def press(self, now, chord=False):
        if self.down:
            return
        self.down = True
        self.down_at = None if chord or now - self.typed_at < ROLLED_SHIFT_SECONDS else now

    def other(self):
        self.down_at, self.down = None, False
        self.typed_at = time.monotonic()

    def release(self, now, chord=False):
        """True when this release ends a tap."""
        tapped = not chord and self.down_at is not None and now - self.down_at <= SHIFT_TAP_SECONDS
        self.down_at, self.down = None, False
        return tapped
