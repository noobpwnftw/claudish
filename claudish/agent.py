"""Claude Code as the agent behind a session (G18), over its stream-json protocol.

The profile's "session_command" starts it, for example:
  ["claude", "--print", "--input-format", "stream-json", "--output-format", "stream-json",
   "--verbose", "--include-partial-messages", "--permission-prompts", "host"]
Claudish is the host: each permission request becomes a question in the candidate list, and the
answer goes back on stdin. Message shapes follow the Agent SDK's control protocol
(claude_agent_sdk/_internal/query.py): control_request can_use_tool -> control_response.
"""
import json
import os
import subprocess
import threading
import time

PARTIAL_EVERY = 0.15  # seconds between partial-draft events


def summarize(tool, arguments):
    """A short legend for what a tool call will do, such as "git push" or "edit app.py"."""
    arguments = arguments if isinstance(arguments, dict) else {}
    for key in ("command", "file_path", "path", "url", "pattern", "query"):
        if isinstance(arguments.get(key), str):
            return "%s: %s" % (tool, arguments[key][:120])
    return tool


class ClaudeCodeDriver:
    def __init__(self, command, timeout=300):
        self.command = list(command)
        self.timeout = timeout
        self.process = None
        self.write_lock = threading.Lock()
        self.pending = {}  # question id (request_id) -> the tool input to allow unchanged
        self.counter = 0

    def send(self, message):
        with self.write_lock:
            if self.process and self.process.poll() is None:
                try:
                    self.process.stdin.write(json.dumps(message) + "\n")
                    self.process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass

    def request(self, body):
        self.counter += 1
        self.send({"type": "control_request", "request_id": "req_%d_%s" % (self.counter, os.urandom(4).hex()),
                   "request": body})

    def run(self, session, prompt):
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                        bufsize=1)
        timer = threading.Timer(self.timeout, self.cancel)
        timer.daemon = True
        timer.start()
        stderr = []
        threading.Thread(target=lambda: stderr.extend(self.process.stderr), daemon=True).start()
        self.request({"subtype": "initialize", "hooks": None})
        self.send({"type": "user", "message": {"role": "user", "content": prompt}, "parent_tool_use_id": None})
        draft, last = "", 0.0
        try:
            for line in self.process.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                kind = message.get("type")
                if kind == "control_request":
                    self.question(session, message)
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
                    if message.get("subtype") == "success" and text and not message.get("is_error"):
                        session.emit("result", text=text)
                    else:
                        session.emit("error", text=text or "the agent stopped: %s" % message.get("subtype"))
                    break
        finally:
            timer.cancel()
            self.close()
        if not session.done:
            tail = "".join(stderr).strip()[-300:]
            session.emit("error", text="the agent exited without a result" + (": " + tail if tail else ""))

    def question(self, session, message):
        body = message.get("request") or {}
        request_id = message.get("request_id")
        if body.get("subtype") != "can_use_tool":
            # Claudish registers no hooks or SDK MCP servers; anything else is declined.
            self.send({"type": "control_response", "response": {
                "subtype": "error", "request_id": request_id, "error": "not supported by this host"}})
            return
        tool = body.get("display_name") or body.get("tool_name") or "a tool"
        self.pending[request_id] = body.get("input") or {}
        session.emit("question", id=request_id, text=body.get("title") or "Allow %s?" % tool,
                     choices=[{"label": "Allow", "legend": body.get("description")
                               or summarize(body.get("tool_name", "tool"), body.get("input"))},
                              {"label": "Deny", "legend": "the agent continues without it"}])

    def answer(self, question, choice=None, text=None):
        if question not in self.pending:
            return
        tool_input = self.pending.pop(question)
        if text is None and choice == 0:
            decision = {"behavior": "allow", "updatedInput": tool_input}
        else:  # Deny, or free text: the user's words go back to the agent as the reason
            decision = {"behavior": "deny", "message": text or "The user declined this tool call."}
        self.send({"type": "control_response", "response": {
            "subtype": "success", "request_id": question, "response": decision}})

    def close(self):
        process = self.process
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

    def cancel(self):
        process = self.process
        if process is not None and process.poll() is None:
            process.kill()
