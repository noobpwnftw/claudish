"""Model processes kept running beside the service: Claude Code and Codex, so a rewrite does not
wait for a CLI to start, and a local model's server (ModelServer).

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

from .modes import TEMPLATES

# The model's whole instruction is cd_AI's own prompt, sent as the message; the CLI's own
# instruction only keeps it from adding an agent's habits around it (templates.json box.cli, the
# profile's).
CLI = TEMPLATES["box"]["cli"]


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


def with_own_folder(command):
    """The environment, with the command's folder first on PATH: an npm install's claude or codex
    is a node script, and its node is beside it (Homebrew's bin, an nvm version's bin), which a
    login service's PATH lacks."""
    folder = os.path.dirname(os.path.expanduser(command))
    path = os.environ.get("PATH", "")
    if not folder or folder in path.split(os.pathsep):
        return None  # the service's own environment
    return dict(os.environ, PATH=folder + os.pathsep + path if path else folder)


class Warm:
    """What both share: a state, a lock (one request at a time), the CLI process, start and stop."""
    name = "the model"
    shaped = False  # its answers are held to claudish/shapes.py's schema

    def __init__(self, command, model=None, cwd=None, restart_after=200, words=None):
        self.command, self.model, self.cwd = list(command), model, cwd
        self.words = words or CLI  # its system instruction and warm-up (templates.json box.cli)
        self.configured = model  # the profile's model (Codex may fall back to its own default)
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
            started = time.monotonic()
            try:
                self.check_running()
                self.launch()
                self.exchange(self.words["ready"], 60)
                self.finish()
            except Exception as exc:
                if isinstance(exc, TimeoutError):  # no network, or a handshake that never came
                    exc = "no answer within %d s" % round(time.monotonic() - started)
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

    def launch(self, deadline=None):
        """The CLI (argv), replacing the one running, its output read as lines; deadline: when the
        request that needs it gives up (Codex's handshake)."""
        import subprocess
        self.kill()
        argv = self.argv()
        self.spawn(argv, self.name, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                   stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                   bufsize=1, cwd=self.cwd, env=with_own_folder(argv[0]))

    def alive(self):
        process = self.process
        return process is not None and process.poll() is None

    def ask(self, prompt, timeout):
        """One rewrite, as its own conversation; RuntimeError with words for the panel. It waits
        for another request (an instruction, the warm-up) no longer than its own timeout."""
        deadline = time.monotonic() + timeout
        if not self.lock.acquire(timeout=timeout):
            raise RuntimeError("%s is busy; keep typing or retry" % self.name)
        try:
            try:
                self.check_running()
                if not self.alive():
                    self.state = "restarting"
                    self.launch(deadline)  # within this request's time, not a handshake's own
                text = self.exchange(prompt, max(0.0, deadline - time.monotonic()))
            except TimeoutError:
                self.failed()  # a stuck one is not reused
                raise RuntimeError("%s took longer than %g s" % (self.name, timeout))
            except (RuntimeError, OSError) as exc:
                self.failed()
                if isinstance(exc, OSError):
                    raise RuntimeError("%s: %s" % (self.name, exc)) from exc
                raise
            try:
                self.finish()  # the next process, ready for the next request
            except Exception:
                self.failed()  # it starts again at the next request; this answer stands
            return text
        finally:
            self.lock.release()

    def failed(self):
        """A request failed: this process is not reused. A fresh one warms up in the background
        (after the request, which holds the lock), as at the service's start: the settings say
        restarting, then warm, or why it failed."""
        with self.lifecycle:
            self.kill(force=True)
            self.state = "stopped" if self.stopped.is_set() else "restarting"
        if not self.stopped.is_set():
            threading.Thread(target=self.warm_up, daemon=True).start()

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

    def retire(self):
        """The process that answered goes, ended in the background: the answer does not wait for it."""
        with self.lifecycle:
            process, self.process = self.process, None
        if process is not None:
            threading.Thread(target=lambda: end_input(process), daemon=True).start()

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

    default_model = "haiku"  # with no "model" in the profile

    def __init__(self, command, model=None, cwd=None, restart_after=200, words=None):
        super().__init__(command, model or self.default_model, cwd, restart_after, words)

    def argv(self):
        return [self.binary()] + self.command[1:] + [
            "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--model", self.model, "--tools", "", "--strict-mcp-config", "--no-session-persistence",
            "--setting-sources", "", "--disable-slash-commands", "--system-prompt", self.words["system"],
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
        """This process answered once; the next request gets a fresh one, started now (the used
        one ends meanwhile)."""
        self.retire()
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

    default_model = "gpt-6-luna"  # with no "model" in the profile

    def __init__(self, command, model=None, cwd=None, restart_after=200, words=None):
        super().__init__(command, model or self.default_model, cwd, restart_after, words)
        self.counter = self.served = 0

    def argv(self):
        off = [part for feature in self.FEATURES_OFF for part in ("--disable", feature)]
        return [self.binary()] + self.command[1:] + ["app-server"] + off

    def launch(self, deadline=None):
        super().launch()
        self.served = 0
        handshake = time.monotonic() + 30
        self.call("initialize", {"clientInfo": {"name": "claudish", "version": "0.1"}},
                  min(handshake, deadline) if deadline else handshake)
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
                  "baseInstructions": self.words["system"], "cwd": self.cwd or os.getcwd()}
        if self.model:
            params["model"] = self.model
        try:
            thread = self.call("thread/start", params, deadline)
        except RuntimeError as exc:
            if not self.model:
                raise
            if "model" in str(exc).lower():
                self.model = None  # not offered on this account: Codex's default model from now on
            params.pop("model")  # another failure (a rate limit): this request only
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
        return texts[-1].strip() if texts else ""  # the final message: an earlier one is commentary

    def ready(self):
        self.served += 1
        if self.served >= self.restart_after:  # loaded threads add up: a fresh process now and then,
            self.retire()  # started by the next request (within its time), not before this answer


def llama_command(server, model, port="18766", gemma=True, gpu_layers="99"):
    """llama-server's argv for a downloaded model (claudish setup --profile local, scripts/run_model.py)."""
    # Gemma 4 thinks first unless told not to, which no request waits for (benchmarks/README.md).
    # --reasoning off holds where a newer chat template ignores enable_thinking (it thought anyway).
    extra = ["--jinja", "--reasoning", "off", "--chat-template-kwargs", '{"enable_thinking":false}', "-c", "4096"] \
        if gemma else ["-c", "2048"]
    return [str(server), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
            "-ngl", str(gpu_layers), "-t", "4", "-np", "1"] + extra


TIMED_OUT = "failed: the local model did not answer within 120 s"


class ModelServer:
    """A local model's server (a llama profile's "command": llama-server's argv), run by the service
    like the CLIs above: started with it, started again when it ends, and stopped when the service
    stops or the settings switch to another model. Requests go to it over HTTP (model_url)."""
    shaped = False

    def __init__(self, command, url):
        self.command, self.url, self.configured = list(command), url.rstrip("/"), None
        self.state = "stopped"
        self.stopped = threading.Event()
        self.guard = threading.Lock()  # the process, between run() and stop()
        self.process = None
        self.ended = False  # stopped by its owner (the service, a settings switch): never retried

    def start(self):
        self.ended = False
        self.stopped.clear()
        self.state = "starting"
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def answers(self):
        from urllib.request import ProxyHandler, build_opener
        try:
            with build_opener(ProxyHandler({})).open(self.url + "/health", timeout=0.5) as response:
                return response.status == 200
        except OSError:
            return False

    def run(self):
        """Start the server and wait until it answers; start it again if it ends after that. One
        that ends before it ever answers (a wrong model path, a port in use, too little memory) has
        failed: started again it would only fail again."""
        import subprocess
        while not self.stopped.is_set():
            if self.answers():  # another server has the port (one left running): this one could not listen
                self.state = "failed: something already answers at %s (a llama-server still running?)" % self.url
                return
            try:
                process = spawn([os.path.expanduser(part) for part in self.command], "the local model",
                                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError as exc:
                self.state = "failed: %s" % (exc,)
                return
            with self.guard:
                if self.stopped.is_set():  # stopped while it started: it is not left running
                    end(process)
                    return
                self.process = process
            deadline = time.monotonic() + 120  # a model loads first
            while process.poll() is None and not self.answers():
                if self.stopped.is_set() or time.monotonic() > deadline:
                    break
                time.sleep(0.2)
            if self.stopped.is_set():
                return
            if process.poll() is not None:
                self.state = "failed: the local model ended as it started (exit %s)" % process.returncode
                return
            if not self.answers():
                with self.guard:  # with the stop, so retry() sees both or neither
                    self.state = TIMED_OUT
                    self.stopped.set()
                    process, self.process = self.process, None
                if process is not None:
                    end(process)
                return
            self.state = "warm"
            process.wait()
            if self.stopped.is_set():
                return
            self.state = "restarting"
            time.sleep(1)

    def retry(self):
        """A request found it failed: one that took too long to load starts again (the next load
        reads the model from the disk cache); one that ended as it started, or a port in use, would
        only fail again."""
        with self.guard:
            if self.ended or self.state != TIMED_OUT:
                return
            self.state = "starting"
        self.start()

    def stop(self):
        with self.guard:
            self.ended = True
            self.stopped.set()
            process, self.process = self.process, None
        if process is not None:
            end(process)
        if self.state != "stopped" and not self.state.startswith("failed"):
            self.state = "stopped"


def end_input(process):
    """A CLI that answered: the end of its input ends it; killed if it does not."""
    try:
        process.stdin.close()
        process.wait(3)
    except Exception:
        process.kill()
        process.wait(3)


def end(process):
    """A child process, ended: asked first, then killed."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(5)
        except Exception:
            process.kill()


def make(backend, command, model=None, cwd=None, words=None):
    return (ClaudeCode if backend == "claude-code" else Codex)(command, model, cwd, words=words)
