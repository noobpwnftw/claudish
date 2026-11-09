"""Claude Code as the agent behind a session (G18), over its stream-json protocol.

The profile's "session_command" starts it, for example:
  ["claude", "--print", "--input-format", "stream-json", "--output-format", "stream-json",
   "--verbose", "--include-partial-messages", "--permission-prompts", "host"]
Claudish is the host: each permission request becomes a question in the candidate list, and the
answer goes back on stdin. One agent process lives per conversation (docs/design/architecture.md), so
follow-up instructions continue the same agent session; a process that ended is resumed by its
session id. Message shapes follow the Agent SDK's control protocol
(claude_agent_sdk/_internal/query.py): control_request can_use_tool -> control_response.
"""
import json
import os
import subprocess
import tempfile
import threading
import time
import uuid

from .children import spawn
from .modes import TEMPLATES
from .warm import with_own_folder

PARTIAL_EVERY = 0.15  # seconds between partial-draft events


def summarize(tool, arguments):
    """A short legend for what a tool call will do, such as "git push" or "edit app.py"."""
    arguments = arguments if isinstance(arguments, dict) else {}
    for key in ("command", "file_path", "path", "url", "pattern", "query"):
        if isinstance(arguments.get(key), str):
            return "%s: %s" % (tool, arguments[key][:120])
    return tool


# An MCP tool call a server runs as a task: answered inside the turn, as any tool's (Claude Code
# 2.1.319 otherwise moves it to the background and tells the model when it finishes, after the
# turn's answer, which an instruction's draft cannot take).
WAIT_FOR_TASKS = {"CLAUDE_CODE_DISABLE_MCP_TASK_BACKGROUND": "1"}


def wire_prefix(server):
    """How Claude Code names an MCP server's tools: mcp__<server>__, the name's other characters as _."""
    from .tools import api_name
    return "mcp__%s__" % api_name(server)


class AgentProcess:
    """One agent process for a conversation: started once, given each turn as a user message."""

    def __init__(self, command, mcp_config=None):
        self.command = list(command)
        self.mcp_config = mcp_config  # Claudish's own MCP servers for this agent (the text box)
        self.config_file = None
        self.session_id = str(uuid.uuid4())
        self.started = False  # once started, a restart resumes the same agent session
        self.kept_at = None  # the last assistant message of the last turn kept (its uuid)
        self.resume_at = None  # set by rewind(): the next process resumes the session at that message
        self.process = None
        self.write_lock = threading.Lock()
        self.turn_lock = threading.Lock()
        self.turns = 0  # turns started; with running, tells an interrupted turn from the next one
        self.running = False
        self.ended = False
        self.counter = 0
        self.stderr = []

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def ensure(self):
        if self.alive():
            return
        if self.ended:  # its conversation ended (idle, or the text box gone): a turn queued behind starts none
            raise RuntimeError("the instruction had ended")
        self.close()  # an agent that exited: its pipes go before it is resumed
        session = []
        if not any(flag in self.command for flag in ("--session-id", "--resume", "--continue")):
            session = ["--resume", self.session_id] if self.started else ["--session-id", self.session_id]
            if self.started and self.resume_at:  # a turn taken back: the session as it was before it
                session += ["--resume-session-at", self.resume_at]
        # resume_at stays until the new process reports (turn()): one that dies first saved nothing,
        # and a plain --resume would bring the turn taken back with it.
        if self.mcp_config and self.config_file is None:
            descriptor, self.config_file = tempfile.mkstemp(prefix="claudish-mcp-", suffix=".json")
            with os.fdopen(descriptor, "w", encoding="utf-8") as config:
                json.dump(self.mcp_config, config)
        if "--permission-prompt-tool" not in self.command:
            # Without it Claude Code denies by itself instead of asking the host (checked live, 2.1.308).
            session += ["--permission-prompt-tool", "stdio"]
        if self.config_file:
            session += ["--mcp-config", self.config_file]  # last: it takes several values
        # No console window on Windows; it ends with its input when the service goes. Not in the
        # service's job: the programs it starts for you stay open, as on Linux and macOS.
        self.process = spawn(self.command + session, "the agent session", job=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                             bufsize=1, env=dict(with_own_folder(self.command[0]) or os.environ, **WAIT_FOR_TASKS))
        # started (--resume from now on) once the agent has answered a turn (turn()): a process
        # that dies before saved no session, and resuming one that does not exist fails every time.
        self.stderr = []
        threading.Thread(target=lambda process=self.process: self.stderr.extend(process.stderr), daemon=True).start()
        self.request({"subtype": "initialize", "hooks": None})

    def send(self, message):
        with self.write_lock:
            if self.alive():
                try:
                    self.process.stdin.write(json.dumps(message) + "\n")
                    self.process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass

    def request(self, body):
        self.counter += 1
        self.send({"type": "control_request", "request_id": "req_%d_%s" % (self.counter, os.urandom(4).hex()),
                   "request": body})

    def rewind(self, to):
        """Take the last turn back from the agent's own session: its next turn starts from `to`,
        the last message of the turn before (None: before any turn, a session of its own)."""
        self.close()
        self.kept_at = to
        if to is None:
            self.session_id, self.started = str(uuid.uuid4()), False
        else:
            self.resume_at = to

    def interrupt(self):
        """Stop the current turn but keep the agent (and its session); kill it if it does not stop."""
        if not self.alive():
            return
        self.request({"subtype": "interrupt"})
        process, turn = self.process, self.turns

        def kill_if_stuck():
            if self.running and self.turns == turn and process.poll() is None:
                process.kill()
        timer = threading.Timer(5, kill_if_stuck)
        timer.daemon = True
        timer.start()

    def close(self, ended=False):
        """Stop the process; ended: the conversation is over (its MCP config goes too)."""
        self.ended = self.ended or ended
        if ended and self.config_file:
            try:
                os.unlink(self.config_file)
            except OSError:
                pass
            self.config_file = None
        process, self.process = self.process, None
        if process is None:
            return
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass


class ClaudeCodeDriver:
    """One turn: the conversation's agent process, its events, and its permission questions."""

    def __init__(self, command, timeout=300, agent=None, context="", policy=None, words=None):
        self.agent = agent or AgentProcess(command)
        self.own = agent is None  # a process of its own (no conversation): closed after the turn
        self.timeout = timeout
        self.context = context  # the text box around the caret, sent with the instruction
        self.words = words or TEMPLATES["box"]  # what a denied or declined call says (the profile's)
        self.policy = policy or {}  # profile tool servers: name -> (trusted tools, denied tools)
        self.pending = {}  # question id (request_id) -> the tool input to allow unchanged
        self.asks = {}  # request_id -> the agent's own questions (AskUserQuestion) and the answers so far
        self.session = None
        self.cancelled = False
        self.ran = None  # the process this turn ran in
        self.before = None  # the agent's kept_at when this turn started; the turn's own last message
        self.reached = None
        self.failed = False  # the turn ended in an error

    @property
    def process(self):
        return self.agent.process or self.ran

    def send(self, message):
        self.agent.send(message)

    def run(self, session, prompt):
        try:
            with self.agent.turn_lock:
                if self.cancelled:  # Esc while an earlier turn of this conversation still ran
                    return
                self.agent.ensure()
                self.agent.turns += 1
                self.agent.running = True  # from here an Esc's interrupt counts this turn (its kill timer)
                if self.cancelled:  # Esc while the agent started: the prompt is never sent
                    self.agent.running = False
                    return
                self.before = self.agent.kept_at
                try:
                    self.turn(session, prompt)
                finally:
                    self.agent.running = False
                if self.cancelled or self.failed:
                    # Esc while it worked, or a turn that failed: the agent's session does not keep it
                    # either (as the model's conversation keeps no failed turn).
                    self.take_back(locked=True)
                elif self.reached:
                    self.agent.kept_at = self.reached
        finally:
            if self.own:  # a process for this turn only ends with it, also when the turn failed
                self.agent.close()

    def watch(self, session, over):
        """The turn's time limit, which your waiting does not count: while a question waits for
        you its own limit runs instead (QUESTION_SECONDS, as for the model's questions). What it
        says comes before the cancel, which would read as Esc."""
        from .conversation import QUESTION_SECONDS
        used, last, asked = 0.0, time.monotonic(), {}  # each question shown -> when
        while not over.wait(0.25):
            now = time.monotonic()
            shown = set(self.pending) | {(request, len(each["answers"])) for request, each in list(self.asks.items())}
            asked = {question: asked.get(question, now) for question in shown}
            if asked:
                if now - min(asked.values()) > QUESTION_SECONDS:
                    session.emit("error", text="no answer, so the instruction stopped")
                    return self.cancel()
            else:
                used += now - last
                if used > self.timeout:
                    session.emit("error", text="the agent took longer than %d s" % self.timeout)
                    return self.cancel()
            last = now

    def turn(self, session, prompt):
        over = threading.Event()
        threading.Thread(target=self.watch, args=(session, over), daemon=True).start()
        self.send({"type": "user", "message": {"role": "user", "content": prompt + self.context}, "parent_tool_use_id": None})
        draft, last = "", 0.0
        process = self.ran = self.agent.process
        try:
            for line in process.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(message, dict):  # JSON, but not a message
                    continue
                kind = message.get("type")
                if kind in ("system", "result", "assistant"):
                    self.agent.started = True  # its session is saved: the next process resumes it
                    self.agent.resume_at = None  # from where it was taken back to
                if kind == "control_request":
                    self.question(session, message)
                elif kind == "system" and message.get("subtype") == "permission_denied":
                    # The agent's own settings said no, without asking: say so in the status line.
                    session.emit("progress", text="%s: not allowed by the agent's settings"
                                 % message.get("tool_name", "a tool"))
                elif kind == "control_cancel_request":
                    # Withdrawn: not waited for (the turn's time runs again); an answer to it is ignored.
                    self.pending.pop(message.get("request_id"), None)
                    self.asks.pop(message.get("request_id"), None)
                elif kind == "stream_event":
                    event = message.get("event") or {}
                    delta = event.get("delta") or {}
                    if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                        draft += delta.get("text", "")
                        if time.monotonic() - last > PARTIAL_EVERY:
                            session.emit("partial", text=draft)
                            last = time.monotonic()
                    elif event.get("type") == "message_start":
                        draft = ""  # a new assistant message: the draft starts over
                elif kind == "assistant" and not message.get("parent_tool_use_id"):
                    self.reached = message.get("uuid") or self.reached  # where this turn has got to
                    for block in (message.get("message") or {}).get("content") or []:
                        if block.get("type") == "tool_use":
                            session.emit("progress", text=summarize(block.get("name", "tool"), block.get("input")))
                elif kind == "result":
                    text = (message.get("result") or "").strip()
                    if self.cancelled:
                        pass  # Esc already ended the session; the agent stopped its turn
                    elif message.get("subtype") == "success" and text and not message.get("is_error"):
                        session.emit("result", text=text)
                    else:
                        self.failed = True
                        session.emit("error", text=text or "the agent stopped: %s" % message.get("subtype"))
                    return
        finally:
            over.set()
        if not session.done and not self.cancelled:  # the process ended mid-turn; the next turn resumes it
            self.failed = True
            tail = "".join(self.agent.stderr).strip()[-300:]
            session.emit("error", text="the agent exited without a result" + (": " + tail if tail else ""))

    def question(self, session, message):
        body = message.get("request") or {}
        request_id = message.get("request_id")
        if body.get("subtype") != "can_use_tool":
            # Claudish registers no hooks or SDK MCP servers; anything else is declined.
            self.send({"type": "control_response", "response": {
                "subtype": "error", "request_id": request_id, "error": "not supported by this host"}})
            return
        name = body.get("tool_name") or ""
        # Claude Code names a server's tools mcp__<server>__<tool>, the server's name with anything
        # but letters, digits, _ and - as _: matched that way, not split at "__" (a server "notes_").
        server, tool = next(((each, name[len(wire_prefix(each)):]) for each in sorted(self.policy, key=len, reverse=True)
                             if name.startswith(wire_prefix(each))), ("", name.partition("__")[2].partition("__")[2]))
        trust, deny = self.policy.get(server, ((), ()))
        if name.startswith("mcp__") and tool in deny:
            self.decide(request_id, {"behavior": "deny", "message": self.words["denied"]})
            return
        if name.startswith("mcp__textbox__") or (name.startswith("mcp__") and tool in trust):
            # Claudish's own read-only tools, and the ones the profile trusts: run without asking.
            self.decide(request_id, {"behavior": "allow", "updatedInput": body.get("input") or {}})
            return
        if name == "AskUserQuestion":
            # The agent asks you something itself: shown as is, its options as the choices (ask).
            self.asks[request_id] = {"input": body.get("input") or {}, "answers": {}}
            self.session = session
            return self.next_question(request_id)
        tool = body.get("display_name") or body.get("tool_name") or "a tool"
        self.pending[request_id] = body.get("input") or {}
        # What is approved is the body, in full; the safe choice (Deny) is listed first and nothing
        # is highlighted (docs/design/design.md).
        tool_input = body.get("input") if isinstance(body.get("input"), dict) else {}
        command = tool_input.get("command")
        label = "Claude Code wants to run" if isinstance(command, str) else "Claude Code wants to use %s" % tool
        shown = command if isinstance(command, str) else (
            body.get("description") or summarize(body.get("tool_name", "tool"), body.get("input")))
        session.emit("question", id=request_id, text=body.get("title") or "Allow %s?" % tool, permission=True,
                     label=label, body=str(shown)[:400], code=isinstance(command, str),
                     choices=[{"label": "Deny", "legend": "the agent continues without it"}, {"label": "Allow"}])

    def next_question(self, request_id):
        """Show the agent's next unanswered question; when all are answered, send the answers."""
        asked = self.asks[request_id]
        questions = [q for q in asked["input"].get("questions") or [] if isinstance(q, dict)]
        if len(asked["answers"]) < len(questions):
            current = questions[len(asked["answers"])]
            self.session.emit("question", id="%s#%d" % (request_id, len(asked["answers"])),
                              text=str(current.get("question") or ""), label="Claude Code asks",
                              body=str(current.get("question") or ""),
                              choices=[{"label": str(option.get("label") or ""),
                                        "legend": str(option.get("description") or "")}
                                       for option in current.get("options") or [] if isinstance(option, dict)])
            return
        del self.asks[request_id]
        self.decide(request_id, {"behavior": "allow", "updatedInput": dict(asked["input"], answers=asked["answers"])})

    def answer(self, question, choice=None, text=None):
        request_id, _, index = str(question).rpartition("#")
        if request_id in self.asks:
            asked = self.asks[request_id]
            current = (asked["input"].get("questions") or [])[int(index)]
            options = [str(o.get("label") or "") for o in current.get("options") or [] if isinstance(o, dict)]
            # Your pick, or your own words (the "Other" answer), keyed by the question's text.
            asked["answers"][str(current.get("question") or "")] = text if text is not None else (
                options[choice] if isinstance(choice, int) and 0 <= choice < len(options) else "")
            return self.next_question(request_id)
        if question not in self.pending:
            return
        tool_input = self.pending.pop(question)
        if text is None and choice == 1:  # Allow, listed after the safe choice
            decision = {"behavior": "allow", "updatedInput": tool_input}
        else:  # Deny, or free text: the user's words go back to the agent as the reason
            decision = {"behavior": "deny", "message": text or self.words["declined"]}
        self.decide(question, decision)

    def decide(self, request_id, decision):
        """The answer to the agent's can_use_tool request: allow or deny."""
        self.send({"type": "control_response", "response": {
            "subtype": "success", "request_id": request_id, "response": decision}})

    def take_back(self, locked=False):
        """Esc as the answer arrived (or while it worked): the agent's own session goes back to
        before this turn, as the conversation does. Only the latest turn, and never under a turn
        running now: a newer one stays."""
        if self.own or self.agent.kept_at not in (self.reached, self.before) or (self.agent.running and not locked):
            return
        if not locked and not self.agent.turn_lock.acquire(blocking=False):
            return  # the next instruction has started: it builds on this one
        try:
            self.agent.rewind(self.before)
        finally:
            if not locked:
                self.agent.turn_lock.release()

    def cancel(self):
        self.cancelled = True
        for question in list(self.pending):  # a waiting permission request is denied
            self.answer(question, 0)
        for request_id in list(self.asks):  # and the agent's own question goes unanswered
            del self.asks[request_id]
            self.decide(request_id, {"behavior": "deny", "message": "The user cancelled."})
        if self.own:
            process = self.agent.process
            if process is not None and process.poll() is None:
                process.kill()
        else:
            self.agent.interrupt()  # the conversation keeps its agent
