"""Conversations per text box, and the model driver that runs each instruction as a turn in one.

Design: docs/design/instruct.md. A conversation belongs to a text box (the adapter sends an id per
input context) and keeps the instructions, the drafts offered and taken, and the tool calls with
their results; the text around the caret is sent fresh each turn. Conversations live only in memory
and end after an idle period. Tool calls go through one policy: read-only tools run, writes ask
(once per conversation if you allow it for the conversation), destructive tools ask every time.
"""
import threading
import time

IDLE_SECONDS = 1800
KEPT_MESSAGES = 60  # the oldest turns go first; a summary would be kinder (docs: compaction)
WINDOW_BEFORE, WINDOW_AFTER = 1500, 500


class Conversation:
    def __init__(self, key):
        self.key = key
        self.messages = []  # earlier turns: user, assistant (with tool calls), tool results
        self.approved = set()  # (server, tool) allowed for this conversation
        self.agent = None  # the agent process, when the profile uses one (session_command)
        self.used = time.monotonic()

    def close(self):
        if self.agent is not None:
            self.agent.close()
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


def window(before, after):
    """The text box around the caret, as reference text for the model."""
    if not (before or after):
        return ""
    before, after = before[-WINDOW_BEFORE:], after[:WINDOW_AFTER]
    return ("\n\n<context name=\"the text box around the caret (▮)\">\n%s%s▮%s%s\n</context>"
            % ("…" if len(before) == WINDOW_BEFORE else "", before, after,
               "…" if len(after) == WINDOW_AFTER else ""))


class ModelDriver:
    """Claudish runs the loop: the model, the profile's tools under the policy, and the conversation."""

    def __init__(self, rewriter, conversation, app=None, before="", after="", look=False):
        self.rewriter, self.conversation = rewriter, conversation
        self.app, self.before, self.after, self.look = app, before, after, look
        self.pending = {}  # question id -> [event, answer]
        self.cancelled = False
        self.counter = 0

    def run(self, session, prompt):
        rewriter = self.rewriter
        if rewriter.backend not in ("llama", "openai"):
            # No conversation or tool loop for this backend yet: one call per turn.
            result = rewriter.rewrite(prompt, self.before, self.after, "instruct", self.app, self.look)
            session.emit("result", text=result["text"], candidates=result.get("candidates") or [result["text"]],
                         consulted=result.get("consulted") or [])
            return
        from .model import user_content
        spec = rewriter.modes["instruct"]
        extra = [p for binding in rewriter.bindings if binding.matches(self.app) for p in binding.providers]
        block, consulted = "", []
        if rewriter.context or extra:
            from .context import Context
            block, consulted = (rewriter.context or Context()).gather("", "", extra)
        image = None
        if self.look:
            from .capture import capture
            image, width, height = capture(rewriter.look_command)
            consulted.append("window picture (%d×%d)" % (width, height))
        system = spec["system"] + block + window(self.before, self.after)
        turn = [{"role": "user", "content": user_content(prompt, image, "openai")}]
        messages = ([{"role": "system", "content": system}] + spec["examples"] + self.conversation.messages + turn)
        max_tokens = spec["max_tokens"] or rewriter.max_tokens

        def ask(messages, tools, **sampling):
            payload = {"messages": messages, "max_tokens": max_tokens, "temperature": 0, "stream": False}
            payload.update(sampling)
            if tools:
                payload["tools"] = tools
            if rewriter.model:
                payload["model"] = rewriter.model
            choice, _ = rewriter.chat(payload, rewriter.request_headers(), image)
            if choice.get("finish_reason") == "length":
                raise RuntimeError("the draft ran past its length budget")
            return choice["message"]

        with_tools = messages
        if rewriter.toolbox:
            guide = ("\n\nYou have tools. When the instruction needs facts you do not have (status, numbers, "
                     "names, contents), call a tool first and write from its result; never invent such facts.")
            messages[0] = {"role": "system", "content": system + guide}
            text, called, with_tools = rewriter.toolbox.run(
                ask, messages, approve=lambda *call: self.approve(session, *call),
                progress=lambda summary: session.emit("progress", text=summary))
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
