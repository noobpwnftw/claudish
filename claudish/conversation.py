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
KEPT_MESSAGES = 60  # the oldest turns go first; a summary would be kinder (docs: compaction)
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


class ModelDriver:
    """Claudish runs the loop: the model, the profile's tools under the policy, and the conversation."""

    def __init__(self, rewriter, conversation, app=None, before="", after="", look=False, purpose=None, screen=None):
        self.rewriter, self.conversation = rewriter, conversation
        self.app, self.before, self.after, self.look, self.purpose = app, before, after, look, purpose
        self.screen = screen  # a terminal's last lines given instead of read (tests)
        self.pending = {}  # question id -> [event, answer]
        self.cancelled = False
        self.counter = 0
        self.handed = None  # what took the task over (a helper), when one did

    def run(self, session, prompt):
        """The instruction as a turn in this text box's conversation: the same one answer as every
        request, with the tools an instruction may use (the profile's, the text box's, a question
        to the user, a helper) and their questions asked through the session."""
        rewriter = self.rewriter
        box = rewriter.box("instruct", self.app, self.purpose, self.before, self.after, self.look, self.screen)
        self.conversation.textbox = Textbox(self.before, self.after)
        local = dict(self.conversation.textbox.tools() if box.clipped() else {})
        local.update(self.own_tools(session, box))
        tools_loop = rewriter.backend in ("llama", "openai")  # no conversation or tools for other backends yet
        self.handed = None
        result = rewriter.answer(
            "instruct", prompt, box, conversation=self.conversation if tools_loop else None,
            approve=lambda *call: self.approve(session, *call),
            progress=lambda summary: session.emit("progress", text=summary), local=local, serial=False)
        if self.cancelled:
            return
        if self.handed:
            # The task went to a helper: nothing is inserted, and the instruction is done.
            session.emit("result", text="", candidates=[], done=self.handed,
                         consulted=result["consulted"] + [self.handed])
            return
        session.emit("result", text=result["text"], candidates=result["candidates"], consulted=result["consulted"])

    def own_tools(self, session, box):
        """Claudish's tools for an instruction: a question to the user (shown as is, the answer goes
        back to the model), and the profile's helper, which acts and so is asked about first."""
        tools = {"user__ask": (
            "Ask the user a short question, shown as is with up to three choices, when the instruction is "
            "ambiguous or needs their decision (\"Did you mean git status?\"). Their answer is the result.",
            {"type": "object", "properties": {
                "question": {"type": "string"},
                "choices": {"type": "array", "items": {"type": "string"}, "maxItems": 3}},
             "required": ["question"]},
            lambda arguments: self.ask_user(session, arguments))}
        from . import handoff
        helper = self.rewriter.helper
        if handoff.available(helper):
            title = handoff.name(helper)

            def hand_over(arguments):
                task = str(arguments.get("task") or "").strip()[:500]
                note = handoff.write_note(task, box.observations)
                if not handoff.launch(helper, note):
                    return "No terminal window could be opened for %s: answer the instruction yourself." % title
                self.handed = "%s opened in a new window" % title
                return "Handed over. Reply with just: OK"
            tools["helper__" + title] = (
                "Hand the task to %s, a coding agent that works on the user's machine in its own terminal "
                "window, when it takes more than an answer here (investigating, editing files, several "
                "steps), or when the user asks for it." % title,
                {"type": "object", "properties": {"task": {"type": "string",
                 "description": "What %s should do, in one or two sentences" % title}}, "required": ["task"]},
                hand_over, "write", lambda arguments: "Send this task to %s?" % title)
        return tools

    def question(self, session, text, choices):
        """A question at the caret; (choice index, your own words) once answered."""
        if self.cancelled:
            return 1, "cancelled"
        self.counter += 1
        key = "question-%d" % self.counter
        waiter = [threading.Event(), None]
        self.pending[key] = waiter
        session.emit("question", id=key, text=text, choices=choices)
        waiter[0].wait()
        return waiter[1] or (1, "cancelled")

    def ask_user(self, session, arguments):
        labels = [str(c)[:80] for c in (arguments.get("choices") or [])][:3] or ["Yes", "No"]
        choice, words = self.question(session, str(arguments.get("question") or "")[:200],
                                      [{"label": label} for label in labels])
        if words is not None:
            return "The user answered: " + words
        return "The user chose: " + labels[choice] if 0 <= choice < len(labels) else "No answer."

    def approve(self, session, server, tool, arguments, kind, asked=None):
        """Ask through the candidate list; (allowed, reason). asked: the question in words (a helper:
        "Send this task to claude?"), else the tool's name."""
        if kind == "write" and (server, tool) in self.conversation.approved:
            return True, None
        shown = ", ".join("%s=%s" % (k, str(v)[:40]) for k, v in arguments.items())
        if asked:
            what = str(arguments.get("task") or shown)[:80]
            choice, text = self.question(session, asked, [{"label": "Yes", "legend": what},
                                                          {"label": "No", "legend": "answer it here instead"}])
            return (False, text) if text is not None else (choice == 0, None)
        legend = "%s.%s(%s)" % (server, tool, shown)
        choices = [{"label": "Allow", "legend": legend}, {"label": "Deny", "legend": "the model continues without it"}]
        if kind == "write":
            choices.append({"label": "Allow for this conversation", "legend": "%s.%s from now on" % (server, tool)})
        choice, text = self.question(session, ("Destructive: allow %s.%s?" if kind == "destructive"
                                               else "Allow %s.%s?") % (server, tool), choices)
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
