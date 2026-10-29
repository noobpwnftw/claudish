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

from .modes import TEMPLATES

PARTIAL_EVERY = 0.15  # seconds between partial-draft events


def summarize(tool, arguments):
    """A short legend for what a tool call will do, such as "git push" or "edit app.py"."""
    arguments = arguments if isinstance(arguments, dict) else {}
    for key in ("command", "file_path", "path", "url", "pattern", "query"):
        if isinstance(arguments.get(key), str):
            return "%s: %s" % (tool, arguments[key][:120])
    return tool


class AgentProcess:
    """One agent process for a conversation: started once, given each turn as a user message."""

    def __init__(self, command, mcp_config=None):
        self.command = list(command)
        self.mcp_config = mcp_config  # Claudish's own MCP servers for this agent (the text box)
        self.config_file = None
        self.session_id = str(uuid.uuid4())
        self.started = False  # once started, a restart resumes the same agent session
        self.process = None
        self.write_lock = threading.Lock()
        self.turn_lock = threading.Lock()
        self.turns = 0  # turns started; with running, tells an interrupted turn from the next one
        self.running = False
        self.counter = 0
        self.stderr = []

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def ensure(self):
        if self.alive():
            return
        self.close()  # an agent that exited: its pipes go before it is resumed
        session = []
        if not any(flag in self.command for flag in ("--session-id", "--resume", "--continue")):
            session = ["--resume", self.session_id] if self.started else ["--session-id", self.session_id]
        if self.mcp_config and self.config_file is None:
            descriptor, self.config_file = tempfile.mkstemp(prefix="claudish-mcp-", suffix=".json")
            with os.fdopen(descriptor, "w", encoding="utf-8") as config:
                json.dump(self.mcp_config, config)
        if "--permission-prompt-tool" not in self.command:
            # Without it Claude Code denies by itself instead of asking the host (checked live, 2.1.308).
            session += ["--permission-prompt-tool", "stdio"]
        if self.config_file:
            session += ["--mcp-config", self.config_file]  # last: it takes several values
        self.process = subprocess.Popen(self.command + session, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                        bufsize=1)
        self.started = True
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

    def __init__(self, command, timeout=300, agent=None, context="", policy=None):
        self.agent = agent or AgentProcess(command)
        self.own = agent is None  # a process of its own (no conversation): closed after the turn
        self.timeout = timeout
        self.context = context  # the text box around the caret, sent with the instruction
        self.policy = policy or {}  # profile tool servers: name -> (trusted tools, denied tools)
        self.pending = {}  # question id (request_id) -> the tool input to allow unchanged
        self.asks = {}  # request_id -> the agent's own questions (AskUserQuestion) and the answers so far
        self.session = None
        self.cancelled = False
        self.ran = None  # the process this turn ran in

    @property
    def process(self):
        return self.agent.process or self.ran

    def send(self, message):
        self.agent.send(message)

    def run(self, session, prompt):
        with self.agent.turn_lock:
            if self.cancelled:  # Esc while an earlier turn of this conversation still ran
                return
            self.agent.ensure()
            self.agent.turns += 1
            self.agent.running = True
            try:
                self.turn(session, prompt)
            finally:
                self.agent.running = False
        if self.own:
            self.agent.close()

    def turn(self, session, prompt):
        timer = threading.Timer(self.timeout, self.cancel)
        timer.daemon = True
        timer.start()
        self.send({"type": "user", "message": {"role": "user", "content": prompt + self.context}, "parent_tool_use_id": None})
        draft, last = "", 0.0
        process = self.ran = self.agent.process
        try:
            for line in process.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                kind = message.get("type")
                if kind == "control_request":
                    self.question(session, message)
                elif kind == "system" and message.get("subtype") == "permission_denied":
                    # The agent's own settings said no, without asking: say so in the status line.
                    session.emit("progress", text="%s: not allowed by the agent's settings"
                                 % message.get("tool_name", "a tool"))
                elif kind == "control_cancel_request":
                    self.pending.pop(message.get("request_id"), None)
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
                        session.emit("error", text=text or "the agent stopped: %s" % message.get("subtype"))
                    return
        finally:
            timer.cancel()
        if not session.done and not self.cancelled:  # the process ended mid-turn; the next turn resumes it
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
        server, _, tool = (body.get("tool_name") or "").partition("__")[2].partition("__")
        trust, deny = self.policy.get(server, ((), ()))
        if (body.get("tool_name") or "").startswith("mcp__") and tool in deny:
            self.send({"type": "control_response", "response": {"subtype": "success", "request_id": request_id,
                       "response": {"behavior": "deny", "message": TEMPLATES["box"]["denied"]}}})
            return
        if (body.get("tool_name") or "").startswith("mcp__textbox__") or \
                ((body.get("tool_name") or "").startswith("mcp__") and tool in trust):
            # Claudish's own read-only tools, and the ones the profile trusts: run without asking.
            self.send({"type": "control_response", "response": {"subtype": "success", "request_id": request_id,
                       "response": {"behavior": "allow", "updatedInput": body.get("input") or {}}}})
            return
        if body.get("tool_name") == "AskUserQuestion":
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
        self.send({"type": "control_response", "response": {"subtype": "success", "request_id": request_id,
                   "response": {"behavior": "allow",
                                "updatedInput": dict(asked["input"], answers=asked["answers"])}}})

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
            decision = {"behavior": "deny", "message": text or TEMPLATES["box"]["declined"]}
        self.send({"type": "control_response", "response": {
            "subtype": "success", "request_id": question, "response": decision}})

    def cancel(self):
        self.cancelled = True
        for question in list(self.pending):  # a waiting permission request is denied
            self.answer(question, 0)
        for request_id in list(self.asks):  # and the agent's own question goes unanswered
            del self.asks[request_id]
            self.send({"type": "control_response", "response": {"subtype": "success", "request_id": request_id,
                       "response": {"behavior": "deny", "message": "The user cancelled."}}})
        if self.own:
            process = self.agent.process
            if process is not None and process.poll() is None:
                process.kill()
        else:
            self.agent.interrupt()  # the conversation keeps its agent
