"""Conversations per text box, and the model driver that runs each instruction as a turn in one.

Design: docs/design/instruct.md. A conversation belongs to a text box (the adapter sends an id per
input context) and keeps the instructions, the drafts offered and taken, and the tool calls with
their results; the text around the caret is sent fresh each turn. Conversations live only in memory
and end after an idle period. Tool calls go through one policy: read-only tools run, writes ask
(once per conversation if you allow it for the conversation), destructive tools ask every time.
"""
import secrets
import threading
import time

from .textbox import Textbox

IDLE_SECONDS = 1800
# Told with the text box (to the model or an agent): the answer is a draft for the caret, not a reply.
AGENT_NOTE = ("\n\nYour answer is inserted at the caret (▮) of the text box above, as the user's own text: "
              "reply with that text only.")
KEPT_MESSAGES = 60  # the oldest turns go first; a summary would be kinder (docs: compaction)
WINDOW_BEFORE, WINDOW_AFTER = 1500, 500
# A model call in an instruction: sent on purpose and awaited, with tools and a long context, so
# it may take far longer than a suggestion while typing (the profile's timeout, if longer).
TURN_TIMEOUT = 60


class Conversation:
    def __init__(self, key):
        self.key = key
        self.messages = []  # earlier turns: user, assistant (with tool calls), tool results
        self.approved = set()  # (server, tool) allowed for this conversation
        self.agent = None  # the agent process, when the profile uses one (session_command)
        self.textbox = Textbox()  # the text box as of the latest instruction (retrieval reads it)
        self.token = secrets.token_hex(16)  # lets this conversation's agent read its text box
        self.used = time.monotonic()

    def close(self):
        if self.agent is not None:
            self.agent.close(ended=True)
            self.agent = None

    def remember(self, messages):
        self.messages = (self.messages + messages)[-KEPT_MESSAGES:]
        while self.messages and self.messages[0]["role"] != "user":  # never start mid-turn
            self.messages.pop(0)


class Conversations:
    def __init__(self):
        self.lock = threading.Lock()
        self.items = {}

    def get(self, key):
        """The conversation for this text box (a new one for an unknown or missing key)."""
        with self.lock:
            now = time.monotonic()
            for old in [k for k, c in self.items.items() if now - c.used > IDLE_SECONDS]:
                self.items.pop(old).close()
            if not key:
                return Conversation(None)
            conversation = self.items.get(key) or Conversation(key)
            conversation.used = now
            self.items[key] = conversation
            return conversation

    def find(self, key):
        """The live conversation for this key, or None (never creates one)."""
        with self.lock:
            return self.items.get(key)

    def end(self, key):
        with self.lock:
            conversation = self.items.pop(key, None)
        if conversation is not None:
            conversation.close()

    def close(self):
        """The service stops: every conversation's agent exits."""
        with self.lock:
            items, self.items = list(self.items.values()), {}
        for conversation in items:
            conversation.close()


# What the input method reported about the field, in words for the model. Free-form text needs none.
KINDS = {"terminal": "a terminal", "email": "an email address field", "url": "a URL field",
         "name": "a name field", "number": "a number field", "phone": "a phone number field",
         "digits": "a digits field", "alpha": "a letters-only field"}


def screen_note(screen):
    """What was consulted, as the candidate window lists it."""
    return "terminal screen (%d lines)" % (screen.count("\n") + 1)


def describe(app, purpose):
    """One line about the text box: its kind and its app, as far as they are known."""
    kind = KINDS.get(purpose or "")
    if not (kind or app):
        return ""
    return "\n\nThe text box is %s%s." % (kind or "a text field", " in %s" % app if app else "")


def terminal(screen):
    """What a terminal means for the result (G35): the text box is its prompt. The screen itself
    goes in the turn, next to the instruction it explains (see in_terminal)."""
    if not screen:
        return ""
    return ("\n\nHere the text box is a terminal's command line: what you write lands at the prompt, "
            "where the user reads it and runs it.")


def in_terminal(screen, text):
    """The turn for an instruction typed at a terminal prompt: what the terminal shows, then the
    instruction (\"fix\" is about the screen, not about an earlier draft)."""
    return "<terminal screen, last lines>\n%s\n</terminal screen>\n\n%s" % (screen, text)


def clipped(before, after):
    """Whether the text box is longer than the window around the caret."""
    return len(before) > WINDOW_BEFORE or len(after) > WINDOW_AFTER


def window(before, after, tools=True):
    """The text box around the caret, as reference text for the model; tools: it can read the rest."""
    if not (before or after):
        return ""
    more = ""
    if clipped(before, after) and tools:
        more = ("\nThe text box has %d characters; this is the part around the caret, at %d. "
                "Read or search the rest with the textbox tools." % (len(before) + len(after), len(before)))
    head = "…" if len(before) > WINDOW_BEFORE else ""
    tail = "…" if len(after) > WINDOW_AFTER else ""
    return ("\n\n<context name=\"the text box around the caret (▮)\">\n%s%s▮%s%s\n</context>%s"
            % (head, before[-WINDOW_BEFORE:], after[:WINDOW_AFTER], tail, more))


class ModelDriver:
    """Claudish runs the loop: the model, the profile's tools under the policy, and the conversation."""

    def __init__(self, rewriter, conversation, app=None, before="", after="", look=False, purpose=None, screen=""):
        self.rewriter, self.conversation = rewriter, conversation
        self.app, self.before, self.after, self.look, self.purpose = app, before, after, look, purpose
        self.screen = screen  # a terminal's last lines, or ""
        self.pending = {}  # question id -> [event, answer]
        self.cancelled = False
        self.counter = 0

    def run(self, session, prompt):
        rewriter = self.rewriter
        if rewriter.backend not in ("llama", "openai"):
            # No conversation or tool loop for this backend yet: one call per turn.
            result = rewriter.rewrite(prompt, self.before, self.after, "instruct", self.app, self.look, self.purpose,
                                      self.screen)
            session.emit("result", text=result["text"], candidates=result.get("candidates") or [result["text"]],
                         consulted=result.get("consulted") or [])
            return
        from .model import user_content
        spec = rewriter.modes["instruct"]
        block, consulted = rewriter.gather(self.app)
        if self.screen:
            consulted.append(screen_note(self.screen))
        image = None
        if self.look:
            from .capture import capture
            image, width, height = capture(rewriter.look_command)
            consulted.append("window picture (%d×%d)" % (width, height))
        context = window(self.before, self.after)
        from .modes import TERMINAL_SYSTEM
        system = ((TERMINAL_SYSTEM if self.screen else spec["system"]) + block + describe(self.app, self.purpose)
                  + context + (AGENT_NOTE if context else "") + terminal(self.screen))
        # At a terminal prompt the screen goes with the instruction it explains, and the template's
        # prose examples stay out.
        said = in_terminal(self.screen, prompt) if self.screen else prompt
        turn = [{"role": "user", "content": user_content(said, image, "openai")}]
        examples = [] if self.screen else spec["examples"]
        messages = ([{"role": "system", "content": system}] + examples + self.conversation.messages + turn)
        max_tokens = spec["max_tokens"] or rewriter.max_tokens

        def ask(messages, tools, **sampling):
            payload = {"messages": messages, "max_tokens": max_tokens, "temperature": 0, "stream": False}
            payload.update(sampling)
            if tools:
                payload["tools"] = tools
            if rewriter.model:
                payload["model"] = rewriter.model
            choice, _ = rewriter.chat(payload, rewriter.request_headers(), image,
                                      timeout=max(rewriter.timeout, TURN_TIMEOUT))
            if choice.get("finish_reason") == "length":
                raise RuntimeError("the draft ran past its length budget")
            return choice["message"]

        with_tools = messages
        self.conversation.textbox = Textbox(self.before, self.after)
        local = self.conversation.textbox.tools() if clipped(self.before, self.after) else {}
        if rewriter.toolbox or local:
            guide = ("\n\nYou have tools. When the instruction needs facts you do not have (status, numbers, "
                     "names, contents), call a tool first and write from its result; never invent such facts.")
            messages[0] = {"role": "system", "content": system + guide}
            from .tools import Toolbox
            text, called, with_tools = (rewriter.toolbox or Toolbox([], {})).run(
                ask, messages, approve=lambda *call: self.approve(session, *call),
                progress=lambda summary: session.emit("progress", text=summary), local=local)
            consulted += called
        else:
            text = (ask(messages, None).get("content") or "").strip()
        if self.cancelled:
            return
        if not text:
            raise RuntimeError("the model offered nothing for this instruction")
        # Readings: the tools ran once; the last turn is sampled again over the same results.
        candidates = [text]
        for index in range(1, spec.get("candidates") or 1):
            try:
                more = (ask(with_tools, None, temperature=0.9, seed=index).get("content") or "").strip()
            except Exception:
                continue
            if more and more not in candidates:
                candidates.append(more)
        # The conversation keeps this turn (the instruction as typed, without the picture).
        kept = [{"role": "user", "content": prompt}] + with_tools[len(messages):]
        self.conversation.remember(kept + [{"role": "assistant", "content": text}])
        session.emit("result", text=candidates[0], candidates=candidates, consulted=consulted)

    def approve(self, session, server, tool, arguments, kind):
        """Ask through the candidate list; (allowed, reason)."""
        if kind == "write" and (server, tool) in self.conversation.approved:
            return True, None
        if self.cancelled:
            return False, "cancelled"
        self.counter += 1
        key = "tool-%d" % self.counter
        shown = ", ".join("%s=%s" % (k, str(v)[:40]) for k, v in arguments.items())
        legend = "%s.%s(%s)" % (server, tool, shown)
        choices = [{"label": "Allow", "legend": legend}, {"label": "Deny", "legend": "the model continues without it"}]
        if kind == "write":
            choices.append({"label": "Allow for this conversation", "legend": "%s.%s from now on" % (server, tool)})
        waiter = [threading.Event(), None]
        self.pending[key] = waiter
        session.emit("question", id=key, choices=choices,
                     text=("Destructive: allow %s.%s?" if kind == "destructive" else "Allow %s.%s?") % (server, tool))
        waiter[0].wait()
        choice, text = waiter[1] or (1, "cancelled")
        if text is not None:
            return False, text  # your words go back to the model as the reason
        if choice == 2:
            self.conversation.approved.add((server, tool))
        return choice in (0, 2), None

    def answer(self, question, choice=None, text=None):
        waiter = self.pending.pop(question, None)
        if waiter:
            waiter[1] = (choice, text)
            waiter[0].set()

    def cancel(self):
        self.cancelled = True
        for waiter in self.pending.values():
            waiter[1] = (1, "cancelled")
            waiter[0].set()
