"""Conversations per text box, and the model driver that runs each instruction as a turn in one.

Design: docs/design/architecture.md. A conversation belongs to a text box (the adapter sends an id per
input context) and keeps the instructions, the first draft of each answer, and the tool calls with
their results; the text around the caret is sent fresh each turn. Conversations live only in memory
and end after an idle period. Tool calls go through one policy: read-only tools run, writes ask
(once per conversation if you allow it for the conversation), destructive tools ask every time.
"""
import secrets
import threading
import time

from .handoff import display_name as handoff_name
from .textbox import Textbox
from .tools import Finished

IDLE_SECONDS = 1800
KEPT_MESSAGES = 60  # the oldest turns go first; a summary would be kinder (docs: compaction)
# A model call in an instruction: sent on purpose and awaited, with tools and a long context, so
# it may take far longer than a suggestion while typing (the profile's timeout, if longer).
TURN_TIMEOUT = 60
QUESTION_SECONDS = 300  # a question nobody answers, as for an agent's (agent.py)
# How a model's own question is shown, and the choice labels only Claudish's own questions use.
MODEL_ASKS = "The model asks: "
MODEL_SAYS = "The model says: "
OWN_LABELS = {"allow", "deny", "allow for this conversation"}


CHOICE_CHARS = 400  # a choice the model offers: a short answer, or a whole draft


def shorten(text, limit):
    """text, or its first limit characters ending in an ellipsis."""
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


class Conversation:
    def __init__(self, key):
        self.key = key
        self.messages = []  # earlier turns: user, assistant (with tool calls), tool results
        self.approved = set()  # (server, tool) allowed for this conversation
        self.agent = None  # the agent process, when the profile uses one (session_command)
        self.textbox = Textbox()  # the text box as of the latest instruction (retrieval reads it)
        self.handoffs = []  # tasks handed to helpers from this text box: {helper, task, session, cwd, started}
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
        self.drafted = None  # drafts a tool chose: versions offered, an answer you inserted, or a helper's command line
        self.settled = None  # what a settling tool did, for this conversation's next turn
        self.draft = None  # a follow-up's draft: the one in view among several (start_session sets it)

    def run(self, session, prompt):
        """The instruction as a turn in this text box's conversation: the same one answer as every
        request, with the tools an instruction may use (the profile's, the text box's, a question
        to the user, a helper) and their questions asked through the session."""
        rewriter = self.rewriter
        box = rewriter.box("instruct", self.app, self.purpose, self.before, self.after, self.look, self.screen)
        box.draft = self.draft
        self.conversation.textbox = Textbox(self.before, self.after)
        local = dict(self.conversation.textbox.tools() if box.clipped() else {})
        local.update(self.own_tools(session, box))
        remembers = rewriter.loops() or rewriter.warm is not None  # Claude Code, Codex: earlier turns in one message
        self.handed = self.drafted = self.settled = None
        try:
            result = rewriter.answer(
                "instruct", prompt, box, conversation=self.conversation if remembers else None,
                approve=lambda *call: self.approve(session, *call),
                progress=lambda summary: self.progress(session, summary), local=local, serial=False)
        except Exception as exc:  # with MCP servers open, a stop arrives wrapped in an exception group
            if self.cancelled:
                return
            if not (self.drafted or self.handed):
                raise
            # An answer you read and chose, or a handoff, ends the turn without asking the model again;
            # the conversation keeps what happened, so the next instruction in this box knows.
            result = {"consulted": []}
            if self.settled:
                self.conversation.remember([{"role": "user", "content": prompt},
                                            {"role": "assistant", "content": self.settled}])
        if self.cancelled:
            return
        if self.drafted:  # versions to pick from, an answer you chose to insert, or a helper's command line
            session.emit("result", text=self.drafted[0], candidates=self.drafted, consulted=result["consulted"])
            return
        if self.handed:
            # The task went to a helper (or an answer was read): nothing is inserted, and the
            # instruction is done.
            session.emit("result", text="", candidates=[], done=self.handed,
                         consulted=result["consulted"] + [self.handed])
            return
        session.emit("result", text=result["text"], candidates=result["candidates"], consulted=result["consulted"])

    def own_tools(self, session, box):
        """Claudish's tools for an instruction: a question to the user (shown as is, the answer goes
        back to the model), and the profile's helper, which acts and so is asked about first."""
        tools = {"user__ask": (
            "Ask the user a short question, shown as is with up to three choices, when the instruction is "
            "ambiguous or needs their decision (\"Did you mean git status?\"), or to offer actions to choose "
            "from, each choice an action. They pick a choice or type a reply; that is the result. The "
            "question goes here, never in your text. Versions of the text to pick from are your answer's "
            "drafts, not a question. Besides your answer, the user sees only this question and user__show.",
            {"type": "object", "properties": {
                "question": {"type": "string"},
                "choices": {"type": "array", "items": {"type": "string"}, "maxItems": 3}},
             "required": ["question"]},
            lambda arguments: self.ask_user(session, arguments))}
        tools["user__show"] = (
            "Show the user an answer to read instead of text for the text box, only when they asked to understand "
            "something (\"what does this error mean?\", \"what is the amount due?\"): a few sentences at most. "
            "Never for something to do: draft it, or hand it over. They may insert it or dismiss it; that ends "
            "the instruction.",
            {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]},
            lambda arguments: self.show(session, arguments, box))
        from . import handoff
        if self.conversation.handoffs:
            tools["helper__check"] = (
                "What the helper you handed a task to from this text box is doing now: its latest messages "
                "(read only; nothing is sent to it). Use it when the user asks about that task (\"is it done?\").",
                {"type": "object", "properties": {}},
                lambda arguments: "\n\n".join(handoff.progress(h) for h in self.conversation.handoffs[-3:]))
        for title, helper in handoff.helpers(self.rewriter.helper).items():
            def hand_over(arguments, title=title, helper=helper):
                import os
                import uuid
                task = str(arguments.get("task") or "").strip()[:500]
                note = handoff.write_note(task, box.observations)
                session = str(uuid.uuid4()) if any("{session}" in part for part in helper) else ""
                # A handle, so a later "is it done?" in this text box can look (G44).
                record = {"helper": title, "task": task, "session": session, "note": note,
                          "tmux": "", "cwd": "", "started": time.time()}
                if box.kind == "terminal":
                    # At a terminal prompt the helper's command is the draft: Tab puts it at the
                    # prompt and your Enter runs it there, in that folder; no window, no question.
                    command = handoff.line(helper, note, session)
                    if command:
                        self.drafted = [command]
                        self.conversation.handoffs.append(record)
                        self.settled = "I offered %s's command at the prompt for this task: %s" % (title, task)
                        raise Finished(self.settled)
                launcher = self.rewriter.launcher
                window = "claudish-%s" % uuid.uuid4().hex[:6] if launcher and "{name}" in launcher else ""
                if not handoff.launch(helper, note, launcher, session, window):
                    return "No terminal window could be opened for %s: answer the instruction yourself." % title
                record.update(tmux=window if launcher and launcher[0] == "tmux" else "", cwd=os.path.expanduser("~"))
                self.conversation.handoffs.append(record)
                self.handed = "%s opened in a new window" % title
                self.settled = "I handed this task to %s in a new window: %s" % (title, task)
                raise Finished(self.settled)
            tools["helper__" + title] = (
                "Hand the task to %s, a coding agent that works on the user's machine (in a terminal, its "
                "command is offered at the prompt; elsewhere in a new terminal window), when it takes more "
                "than an answer here (investigating, editing files, several steps), or when the user asks "
                "for it." % title,
                {"type": "object", "properties": {"task": {"type": "string",
                 "description": "What %s should do, in one or two sentences" % title}}, "required": ["task"]},
                hand_over, "read" if box.kind == "terminal" else "write",
                lambda arguments, title=title: "Send this task to %s?" % title)
        return tools

    def question(self, session, text, choices, kind="ask", label=None, body=None, code=False, read=False,
                 insert=None):
        """A question at the caret; (choice index, your own words) once answered. kind: "ask" (the
        model's own question: its first choice highlighted, Tab answers) or "permission" (an
        approval: nothing highlighted until ↓, which lands on its safe choice, listed first; a
        reflexive key approves nothing). label and body: how the panel shows it (who asks, then
        what)."""
        if self.cancelled:
            return 1, "cancelled"
        self.counter += 1
        key = "question-%d" % self.counter
        waiter = [threading.Event(), None]
        self.pending[key] = waiter
        session.emit("question", id=key, text=text, choices=choices, permission=kind == "permission",
                     label=label, body=text if body is None else body, code=code, read=read,
                     **({"insert": insert} if insert is not None else {}))
        if not waiter[0].wait(QUESTION_SECONDS):  # nobody answered: the instruction ends, as on Esc
            self.pending.pop(key, None)
            self.cancel()  # a model told "no answer" asks again; the loop stops at its next call
            session.emit("error", text="no answer, so the instruction stopped")
            return 1, "no answer"
        return waiter[1] or (1, "cancelled")

    def show(self, session, arguments, box):
        """An answer to read, shown as is (marked as the model's): Insert puts it at the caret,
        Dismiss ends the instruction with nothing inserted."""
        text = str(arguments.get("answer") or "").strip()[:1000]
        if not text:
            return "Nothing to show."
        fitted = box.fit("instruct", text)  # inserted like any answer: a terminal takes one line
        # Tab inserts `insert` at once, in the input method; the choice comes back to record it.
        choice, words = self.question(session, MODEL_SAYS + text,
                                      [{"label": "Insert it", "legend": "at the caret"},
                                       {"label": "Dismiss", "legend": "nothing is inserted"}],
                                      label=MODEL_SAYS.rstrip(": "), body=text, read=True, insert=fitted)
        if words:  # "or type to ask more": your words go to the model, and the turn goes on
            return "The user read it and asked: " + words
        if choice == 0:
            self.drafted = [fitted]
            self.settled = "I showed the user this answer, and they inserted it: " + text
        else:
            self.handed = "read and dismissed"
            self.settled = "I showed the user this answer, and they dismissed it: " + text
        raise Finished(self.settled)

    def ask_user(self, session, arguments):
        """The model's own question, shown as is and marked as the model's."""
        from .screen import redact
        # A choice can be a whole draft (the panel wraps it); a longer one says it was cut.
        labels = [shorten(str(c), CHOICE_CHARS) for c in (arguments.get("choices") or [])][:3] or ["Yes", "No"]
        labels = [label for label in labels if label.strip().lower() not in OWN_LABELS] or ["Yes", "No"]
        asked = shorten(str(arguments.get("question") or ""), 400)
        choice, words = self.question(session, MODEL_ASKS + asked, [{"label": label} for label in labels],
                                      label=MODEL_ASKS.rstrip(": "), body=asked)
        if words is not None:
            return "The user answered: " + redact(words)[0]
        return "The user chose: " + labels[choice] if 0 <= choice < len(labels) else "No answer."

    def approve(self, session, server, tool, arguments, kind, asked=None):
        """Ask through the candidate list; (allowed, reason). asked: the question in words (a helper:
        "Send this task to claude?"), else the tool's name."""
        if kind == "write" and (server, tool) in self.conversation.approved:
            return True, None
        shown = ", ".join("%s=%s" % (k, str(v)[:40]) for k, v in arguments.items())
        if asked:
            # The whole task, in the question itself: nothing the helper will be told is hidden.
            # The safe choice (No) is first: the first ↓ lands on it, so nothing is handed over by reflex.
            what = str(arguments.get("task") or shown)
            choice, text = self.question(session, "%s %s" % (asked, what),
                                         [{"label": "No", "legend": "answer it here"},
                                          {"label": "Yes", "legend": "it opens in a new window"}], kind="permission",
                                         label="Hand off to %s" % handoff_name(tool), body=what)
            return (False, text) if text is not None else (choice == 1, None)
        call = "%s.%s(%s)" % (server, tool, shown)
        choices = [{"label": "Deny", "legend": "the model continues without it"}, {"label": "Allow"}]
        if kind == "write":
            choices.append({"label": "Allow for this conversation", "legend": "%s.%s from now on" % (server, tool)})
        choice, text = self.question(session, ("Destructive: allow %s.%s?" if kind == "destructive"
                                               else "Allow %s.%s?") % (server, tool), choices, kind="permission",
                                     label="The model wants to %s" % ("change something with" if kind == "destructive"
                                                                       else "use"),
                                     body=call, code=True)
        if text is not None:
            return False, text  # your words go back to the model as the reason
        if choice == 2:
            self.conversation.approved.add((server, tool))
        return choice in (1, 2), None

    def answer(self, question, choice=None, text=None):
        waiter = self.pending.pop(question, None)
        if waiter:
            waiter[1] = (choice, text)
            waiter[0].set()

    def progress(self, session, summary):
        """Each tool call, as it happens; after Esc the loop stops at the next one."""
        if self.cancelled:
            raise RuntimeError("cancelled")
        session.emit("progress", text=summary)

    def cancel(self):
        self.cancelled = True
        for waiter in self.pending.values():
            waiter[1] = (1, "cancelled")
            waiter[0].set()
