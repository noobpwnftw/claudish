"""Warm subscription backends: Claude Code and Codex kept running beside the service, as the local
model is, so a rewrite does not wait for a CLI to start.

- Claude Code: `claude -p` in stream-json mode, started ahead of time and used for one request,
  then replaced by the next one already started (each request is its own conversation).
- Codex: one `codex app-server`, a new ephemeral thread for each request.

Both start with the service, answer one readiness exchange, are restarted when they die, and end
when the service ends (claudish/children.py). State: "starting", "warm", "restarting", or
"failed: why"."""
import json
import os
import queue
import threading
import time

from .children import spawn
from .shapes import ANSWER

# The model's whole instruction is cd_AI's own prompt, sent as the message; this only keeps the
# CLI from adding an agent's habits around it.
NEUTRAL = "Do exactly what the user's message asks. Output only the result, nothing else."
READY = "Reply with the single word: ready"


class Lines:
    """A child's stdout as lines, read on a thread (pipes cannot be polled on Windows)."""

    def __init__(self, stream):
        self.queue = queue.Queue()
        threading.Thread(target=self.pump, args=(stream,), daemon=True).start()

    def pump(self, stream):
        try:
            for line in stream:
                self.queue.put(line)
        finally:
            stream.close()
            self.queue.put(None)

    def next(self, deadline):
        """The next line, None at end of output; TimeoutError past the deadline."""
        try:
            return self.queue.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            raise TimeoutError from None


class Warm:
    """What both share: a state, a lock (one request at a time), the CLI process, start and stop."""
    name = "the model"
    shaped = False  # its answers are held to claudish/shapes.py's schema

    def __init__(self, command, model=None, cwd=None, restart_after=200):
        self.command, self.model, self.cwd = list(command), model, cwd
        self.restart_after = restart_after
        self.state = "stopped"
        self.lock = threading.Lock()
        self.lifecycle = threading.RLock()
        self.stopped = threading.Event()
        self.process = self.lines = None

    def start(self):
        """At service start: warm up in the background; the service answers meanwhile."""
        self.stopped.clear()
        self.state = "starting"
        threading.Thread(target=self.warm_up, daemon=True).start()

    def warm_up(self):
        with self.lock:
            try:
                self.check_running()
                self.launch()
                self.exchange(READY, 60)
                self.finish()
            except Exception as exc:
                with self.lifecycle:
                    self.kill(force=True)
                    self.state = "stopped" if self.stopped.is_set() else "failed: %s" % (exc,)

    def check_running(self):
        if self.stopped.is_set():
            raise RuntimeError("cd_AI is stopping")

    def finish(self):
        self.check_running()
        self.ready()
        with self.lifecycle:
            self.check_running()
            self.state = "warm"

    def spawn(self, *args, **kwargs):
        with self.lifecycle:
            self.check_running()
            if self.cwd:
                os.makedirs(self.cwd, exist_ok=True)
            self.process = spawn(*args, **kwargs)
            self.lines = Lines(self.process.stdout)

    def launch(self):
        """The CLI (argv), replacing the one running, its output read as lines."""
        import subprocess
        self.kill()
        self.spawn(self.argv(), self.name, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                   stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                   bufsize=1, cwd=self.cwd)

    def alive(self):
        process = self.process
        return process is not None and process.poll() is None

    def ask(self, prompt, timeout):
        """One rewrite, as its own conversation; RuntimeError with words for the panel."""
        with self.lock:
            try:
                self.check_running()
                if not self.alive():
                    self.state = "restarting"
                    self.launch()
                text = self.exchange(prompt, timeout)
                self.finish()
            except TimeoutError:
                self.failed()  # a stuck one is not reused
                raise RuntimeError("%s took longer than %g s" % (self.name, timeout))
            except (RuntimeError, OSError) as exc:
                self.failed()
                if isinstance(exc, OSError):
                    raise RuntimeError("%s: %s" % (self.name, exc)) from exc
                raise
            return text

    def failed(self):
        with self.lifecycle:
            self.kill(force=True)
            self.state = "stopped" if self.stopped.is_set() else "restarting"

    def stop(self):
        self.stopped.set()
        with self.lifecycle:
            self.kill(force=True)
            self.state = "stopped"

    def binary(self):
        """The CLI's path; found again when an update moved it (as run_command does)."""
        program = os.path.expanduser(self.command[0])
        if not os.path.exists(program):
            from . import settings
            name = os.path.basename(program).lower()
            program = (settings.codex() if name.startswith("codex") else settings.claude_code()) or program
        return program

    def kill(self, force=False):
        with self.lifecycle:
            process, self.process = self.process, None
            if process is not None and process.poll() is None:
                try:
                    if force:
                        raise TimeoutError
                    process.stdin.close()  # the end of its input: it ends
                    process.wait(3)
                except Exception:
                    process.kill()
                    process.wait(3)
            if process is not None and process.stdin is not None:
                process.stdin.close()


class ClaudeCode(Warm):
    """`claude -p --input-format stream-json`: one process per request, started before it is needed.
    Its answers are held to the drafts schema (--json-schema; claudish/shapes.py)."""
    name = "Claude Code"
    shaped = True

    def __init__(self, command, model="haiku", cwd=None, restart_after=200):
        super().__init__(command, model or "haiku", cwd, restart_after)

    def argv(self):
        return [self.binary()] + self.command[1:] + [
            "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--model", self.model, "--tools", "", "--strict-mcp-config", "--no-session-persistence",
            "--setting-sources", "", "--disable-slash-commands", "--system-prompt", NEUTRAL,
            "--json-schema", json.dumps(ANSWER)]

    def exchange(self, prompt, timeout):
        self.check_running()
        process, lines = self.process, self.lines
        if process is None:
            raise RuntimeError("Claude Code ended")
        deadline = time.monotonic() + timeout
        message = {"type": "user", "message": {"role": "user", "content": prompt}}
        try:
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
        except (OSError, ValueError):
            raise RuntimeError("Claude Code ended: %s" % self.why())
        while True:
            line = lines.next(deadline)
            if line is None:
                raise RuntimeError("Claude Code ended: %s" % self.why())
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "result":
                if event.get("is_error"):
                    raise RuntimeError("Claude Code: %s" % (event.get("result") or event.get("subtype") or "failed"))
                if isinstance(event.get("structured_output"), dict):  # the schema's answer, as data
                    return json.dumps(event["structured_output"], ensure_ascii=False)
                return (event.get("result") or "").strip()

    def ready(self):
        """This process answered once; the next request gets a fresh one, started now."""
        self.launch()

    def why(self):
        try:
            return "exit %s" % self.process.wait(2)
        except Exception:
            return "no reason given"


class Codex(Warm):
    """`codex app-server`: one process; each request a new ephemeral, read-only thread."""
    name = "Codex"
    shaped = True
    FEATURES_OFF = ("apps", "plugins", "multi_agent", "image_generation", "computer_use", "browser_use",
                    "shell_tool", "skill_search", "tool_suggest", "hooks")

    def __init__(self, command, model="gpt-6-luna", cwd=None, restart_after=200):
        super().__init__(command, model or "gpt-6-luna", cwd, restart_after)
        self.counter = self.served = 0

    def argv(self):
        off = [part for feature in self.FEATURES_OFF for part in ("--disable", feature)]
        return [self.binary()] + self.command[1:] + ["app-server"] + off

    def launch(self):
        super().launch()
        self.served = 0
        self.call("initialize", {"clientInfo": {"name": "claudish", "version": "0.1"}}, time.monotonic() + 30)
        self.send({"jsonrpc": "2.0", "method": "initialized"})

    def send(self, message):
        process = self.process
        if process is None:
            raise RuntimeError("Codex ended")
        try:
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
        except (OSError, ValueError):
            raise RuntimeError("Codex ended")

    def call(self, method, params, deadline, collect=None):
        """A request; its result. collect(notification) sees what arrives meanwhile."""
        self.counter += 1
        ident = self.counter
        self.send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        while True:
            message = self.read(deadline, collect)
            if message.get("id") == ident and "method" not in message:
                if "error" in message:
                    raise RuntimeError("Codex: %s" % (message["error"].get("message") or message["error"]))
                return message.get("result") or {}

    def read(self, deadline, collect=None):
        line = self.lines.next(deadline)
        if line is None:
            raise RuntimeError("Codex ended")
        try:
            message = json.loads(line)
        except ValueError:
            return {}
        if "method" in message and "id" in message:  # a request from Codex (an approval): no
            self.send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "declined"}})
        elif "method" in message and collect:
            collect(message)
        return message

    def exchange(self, prompt, timeout):
        deadline = time.monotonic() + timeout
        params = {"ephemeral": True, "sandbox": "read-only", "approvalPolicy": "never",
                  "baseInstructions": NEUTRAL, "cwd": self.cwd or os.getcwd()}
        if self.model:
            params["model"] = self.model
        try:
            thread = self.call("thread/start", params, deadline)
        except RuntimeError:
            if not self.model:
                raise
            self.model = None  # not offered on this account: Codex's default model instead
            params.pop("model")
            thread = self.call("thread/start", params, deadline)
        thread_id = thread["thread"]["id"]
        texts, done = [], []

        def collect(message):
            item = (message.get("params") or {}).get("item") or {}
            if message["method"] == "item/completed" and item.get("type") == "agentMessage":
                texts.append(item.get("text") or "")
            if message["method"] == "turn/completed":
                done.append(message["params"])
        self.call("turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": prompt}],
                                 "effort": "low", "outputSchema": ANSWER}, deadline, collect)
        while not done:
            self.read(deadline, collect)
        error = ((done[0].get("turn") or {}).get("error") or {})
        if error and not texts:
            raise RuntimeError("Codex: %s" % (error.get("message") or error))
        return "\n".join(texts).strip()

    def ready(self):
        self.served += 1
        if self.served >= self.restart_after:  # loaded threads add up: a fresh process now and then
            self.launch()


def make(backend, command, model=None, cwd=None):
    return (ClaudeCode if backend == "claude-code" else Codex)(command, model, cwd)
