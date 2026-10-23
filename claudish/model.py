import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

SYSTEM = (
    "Rewrite the user's text in polished, slightly verbose English. "
    "Keep its meaning, names, numbers and language. Use an em dash where natural. "
    "Output only the rewritten text, no explanation."
)

EXAMPLES = [
    {"role": "user", "content": "We need to think about this."},
    {"role": "assistant", "content": "This warrants thoughtful consideration—a chance to examine the nuances."},
]


def load_prompt(path):
    """Read a rewrite template: {"system": "...", "examples": [["input", "rewrite"], ...]}."""
    with open(path, encoding="utf-8") as source:
        data = json.load(source)
    system, examples = data.get("system"), data.get("examples", [])
    if not isinstance(system, str) or not system.strip():
        raise ValueError("prompt file needs a non-empty \"system\" string")
    if not all(isinstance(pair, list) and len(pair) == 2 and all(isinstance(s, str) for s in pair)
               for pair in examples):
        raise ValueError("prompt \"examples\" must be [input, rewrite] string pairs")
    return system, [message for source_text, rewrite in examples for message in (
        {"role": "user", "content": source_text}, {"role": "assistant", "content": rewrite})]


def rules(text):
    """Explicit model-free demo, not a substitute for neural rewriting."""
    text = text.replace("--", "—")
    for word, replacement in [("use", "leverage"), ("explore", "delve into"),
                              ("important", "crucial"), ("very", "particularly")]:
        def replace(match):
            value = replacement
            if match[0].isupper():
                return value.upper()
            return value.capitalize() if match[0][0].isupper() else value
        text = re.sub(r"\b" + word + r"\b", replace, text, flags=re.IGNORECASE)
    return text


def user_content(text, image, style):
    """The user turn: the text, or the text after a picture of the focused window (PNG bytes)."""
    if image is None:
        return text
    data = base64.b64encode(image).decode("ascii")
    if style == "claude":
        picture = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}
    else:  # OpenAI-compatible: llama.cpp with a vision model (--mmproj), vLLM, Ollama, hosted APIs
        picture = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + data}}
    return [picture, {"type": "text", "text": "The picture is the window I am typing in.\n\n" + text}]


class Claude:
    """Opt-in hosted backend: typed text is sent to the Anthropic API."""

    def __init__(self, model):
        import anthropic  # Optional dependency: pip install "claudish-ime[claude]"
        # Credentials come from ANTHROPIC_API_KEY or an `ant auth login` profile.
        # A stale suggestion is useless, so fail fast instead of retrying.
        self.client = anthropic.Anthropic(timeout=10.0, max_retries=0)
        self.model = model

    def rewrite(self, text, system, examples, image=None):
        options = {}
        if not self.model.startswith("claude-haiku"):  # Haiku has no server-side fallback.
            options = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            response = self.client.beta.messages.create(
                model=self.model, max_tokens=2048, system=system,
                messages=examples + [{"role": "user", "content": user_content(text, image, "claude")}],
                output_config={"effort": "low"}, **options)
        except TypeError as exc:  # Raised by the SDK before any request when no credentials resolve.
            if "authentication" not in str(exc):
                raise
            raise RuntimeError("no Claude credentials: set ANTHROPIC_API_KEY or run `ant auth login`") from exc
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined this rewrite; your wording is unchanged")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("rewrite exceeded token budget; use a shorter phrase")
        output = "".join(block.text for block in response.content if block.type == "text").strip()
        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        return output, usage


class Rewriter:
    """backend: "llama"/"openai" (any OpenAI-compatible server), "claude", or "rules"."""

    @classmethod
    def from_settings(cls, settings, prompt=None, context=None, profile=None):
        """Build from config.resolve() output. ValueError if the profile's key variable is unset;
        ImportError if the claude backend lacks the Anthropic SDK."""
        api_key = None
        if settings["api_key_env"]:
            api_key = os.environ.get(settings["api_key_env"])
            if not api_key:
                raise ValueError("environment variable %s is not set" % settings["api_key_env"])
        rewriter = cls(settings["backend"], settings["model_url"], settings["max_tokens"], settings["claude_model"],
                       settings["model"], api_key, settings["timeout"], prompt, context, settings["modes"],
                       settings["command"], settings["hosted"], settings["bindings"])
        rewriter.profile = profile
        rewriter.look_command = settings.get("look_command")
        rewriter.read_terminal = settings.get("read_terminal", True)
        rewriter.session_command = settings.get("session_command")
        if settings.get("tools"):
            if settings["backend"] not in ("llama", "openai"):
                raise ValueError("tools need an OpenAI-compatible backend with tool calls (llama.cpp, vLLM, Ollama) "
                                 "for now; the %s backend cannot use them yet" % settings["backend"])
            from .tools import Toolbox
            rewriter.toolbox = Toolbox(settings["tools"], settings.get("mcp_servers") or {})
        return rewriter

    def __init__(self, backend="llama", endpoint="http://127.0.0.1:18766", max_tokens=64,
                 claude_model="claude-opus-5-5", model=None, api_key=None, timeout=3, prompt=None,
                 context=None, modes=None, command=None, hosted=None, bindings=()):
        from . import modes as invocation
        self.backend = backend
        self.endpoint = endpoint.rstrip("/")
        self.max_tokens = max_tokens
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.system, self.examples = prompt or (SYSTEM, EXAMPLES)
        self.context = context
        self.bindings = list(bindings)
        from .sessions import Sessions
        self.sessions = Sessions()  # instructions as sessions: events, questions, a result (G18)
        from .conversation import Conversations
        self.conversations = Conversations()  # one per text box (docs/design/instruct.md)
        self.session_command = None  # profile "session_command": a stream-json agent such as Claude Code
        self.toolbox = None  # profile "tools": read-only MCP tools an instruction may call (G17)
        self.look_command = None  # profile "look_command": argv that writes a PNG of the focused window
        self.read_terminal = True  # profile "read_terminal": a terminal's last lines go with an instruction
        # name -> {"system", "examples", "max_tokens"}; a profile may replace any mode's template.
        self.modes = invocation.defaults((self.system, self.examples))
        for name, override in (modes or {}).items():
            self.modes[name] = dict(self.modes.get(name, {"max_tokens": None}), **override)
        self.finish = invocation.finish
        self.lock = threading.Lock()
        self.local = urlsplit(self.endpoint).hostname in ("127.0.0.1", "localhost", "::1")
        self.opener = None
        self.hosted = backend == "claude" or (backend in ("llama", "openai") and not self.local)
        if backend == "command":
            if not command:
                raise ValueError('the command backend needs a "command" list in the profile')
            self.command = command
            self.hosted = True if hosted is None else hosted  # Most agent CLIs call a remote model.
        self.claude = Claude(claude_model) if backend == "claude" else None

    def complete(self, payload, headers, image=None):
        """One chat completion from an OpenAI-compatible server: (text, usage)."""
        choice, usage = self.chat(payload, headers, image)
        # Never offer a sentence chopped off by the token limit.
        if choice.get("finish_reason") == "length":
            raise RuntimeError("rewrite exceeded token budget; use a shorter phrase")
        output = (choice["message"].get("content") or "").strip()
        if not output:
            raise RuntimeError("model returned no text")
        return output, usage

    def terminal(self, app, purpose, mode):
        """(purpose, screen): in a terminal (by the field's kind or the app), say so, and for a rewrite
        or an instruction read its last lines (G35); never for continue's pauses."""
        from .screen import is_terminal, read
        if purpose != "terminal" and not is_terminal(app):
            return purpose, ""
        if mode == "continue" or not self.read_terminal:
            return "terminal", ""
        return "terminal", read(app) or ""

    def make_driver(self, app=None, conversation=None, before="", after="", look=False, purpose=None, screen=None):
        """The driver for an instruction: the profile's agent (session_command), else the model
        driver, which runs it as a turn in the text box's conversation. screen: a terminal's last
        lines, read here when None."""
        if screen is None:
            purpose, screen = self.terminal(app, purpose, "instruct")
        if self.session_command:
            from .agent import AgentProcess, ClaudeCodeDriver
            if not conversation:
                return ClaudeCodeDriver(self.session_command)  # a process for this turn only
            from .conversation import AGENT_NOTE, describe, terminal, window
            from .textbox import Textbox
            kept = self.conversations.get(conversation)
            kept.textbox = Textbox(before, after)  # what its textbox tools read this turn
            textbox = getattr(self, "url", None) and "textbox" in ((self.agent_mcp_config(kept) or {}).get("mcpServers") or {})
            kept.agent = kept.agent or AgentProcess(self.session_command + self.agent_arguments(),
                                                    self.agent_mcp_config(kept))
            block, _ = self.gather(app, before, after)  # the profile's context and the app's bindings
            place = window(before, after, tools=bool(textbox))
            context = block + describe(app, purpose) + place
            if place:
                context += AGENT_NOTE + (" The textbox tools (read, search) see all of it." if textbox else "")
            context += terminal(screen)
            policy = self.toolbox.policy() if self.toolbox else {}
            return ClaudeCodeDriver(self.session_command, agent=kept.agent, context=context, policy=policy)
        from .conversation import ModelDriver
        return ModelDriver(self, self.conversations.get(conversation), app, before, after, look, purpose, screen)

    def gather(self, app=None, before="", after=""):
        """(context block, what was consulted): the profile's context, plus the bindings for the
        focused app (a supported text box). The same for every mode and both drivers."""
        extra = [provider for binding in self.bindings if binding.matches(app) for provider in binding.providers]
        if not (self.context or extra):
            return "", []
        from .context import Context
        return (self.context or Context()).gather(before, after, extra)

    def agent_mcp_config(self, conversation):
        """--mcp-config for an agent: the profile's tool servers (as configured for Claudish, not the
        agent's own), and Claudish's textbox server when the MCP SDK is here to run it."""
        import importlib.util
        servers = dict(self.toolbox.configs) if self.toolbox else {}
        url = getattr(self, "url", None)
        if url and importlib.util.find_spec("mcp") is not None:
            package = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            servers["textbox"] = {
                "command": sys.executable, "args": ["-m", "claudish", "textbox-mcp"],
                "env": {"CLAUDISH_URL": url, "CLAUDISH_CONVERSATION": conversation.key,
                        "CLAUDISH_TOKEN": conversation.token, "PYTHONPATH": package}}
        return {"mcpServers": servers} if servers else None

    def agent_arguments(self):
        """Extra agent CLI arguments from the policy: denied tools are never offered."""
        denied = ["mcp__%s__%s" % (server, tool) for server, (_, deny) in (self.toolbox.policy().items()
                                                                          if self.toolbox else ()) for tool in sorted(deny)]
        return ["--disallowedTools", ",".join(denied)] if denied else []

    def start_session(self, text, app=None, conversation=None, before="", after="", look=False, purpose=None,
                      screen=None):
        return self.sessions.start(self.make_driver(app, conversation, before, after, look, purpose, screen), text)

    def request_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        return headers

    def chat(self, payload, headers, image=None, timeout=None):
        """(the first choice, usage) from /v1/chat/completions; timeout: seconds, else the profile's."""
        req = Request(self.endpoint + "/v1/chat/completions", data=json.dumps(payload).encode(), headers=headers)
        # Loopback traffic must not go through HTTP_PROXY; a remote endpoint may need it.
        # Built once: build_opener() loads the system CA bundle, about 12 ms per call.
        if self.opener is None:
            self.opener = build_opener(ProxyHandler({})) if self.local else build_opener()
        try:
            with self.opener.open(req, timeout=timeout or self.timeout) as response:
                data = json.load(response)
        except HTTPError as exc:
            if image is not None and exc.code in (400, 500, 501):
                raise RuntimeError("this model server did not accept the window picture; it needs a vision "
                                   "model (llama.cpp: --mmproj)") from exc
            raise
        return data["choices"][0], data.get("usage", {})

    def rewrite(self, text, before="", after="", mode="rewrite", app=None, look=False, purpose=None, screen=None,
                context=True):
        """look: attach a picture of the focused window (instruct only; the user asked for it with F8).
        before/after: the text box around the caret, where the result goes (continue: the text is
        what comes before, so only after adds); purpose: the field's kind; screen: a terminal's
        last lines, read here when None; context: False for the demo's requests (no token): the
        profile's context and bindings are not used."""
        started = time.perf_counter()
        if mode not in self.modes:
            raise ValueError("unknown mode %r; available: %s" % (mode, ", ".join(self.modes)))
        image = None
        if look:
            if mode != "instruct":
                raise ValueError("a window picture is only taken for an instruction")
            if self.backend == "command":
                raise RuntimeError("the command backend cannot take a window picture; use claude or a vision model")
            from .capture import capture
            image, width, height = capture(self.look_command)
        if screen is None:
            purpose, screen = self.terminal(app, purpose, mode) if context else (purpose, "")
        elif screen:
            purpose = "terminal"
        spec = self.modes[mode]
        block, consulted = self.gather(app, before, after) if context else ("", [])
        if screen:
            from .conversation import screen_note
            consulted = consulted + [screen_note(screen)]
        if image is not None:
            consulted = consulted + ["window picture (%d×%d)" % (width, height)]
        # The text box, described the same way for every mode: its kind and app, and the text around
        # where the result goes.
        from .conversation import describe, terminal, window
        place = window("", after) if mode == "continue" else window(before, after)
        system = spec["system"] + block + describe(app, purpose) + place + terminal(screen)
        examples, max_tokens = spec["examples"], spec["max_tokens"] or self.max_tokens
        # What the model is sent: the text itself, or the mode's frame around it (continue).
        sent = spec["frame"].replace("{text}", text) if spec.get("frame") else text
        count = spec.get("candidates") or 1
        if self.backend == "rules":
            # Deterministic stand-ins so the demo and tests work without a model.
            output = {"rewrite": rules(text), "continue": "and then some—naturally.",
                      "instruct": "As requested—" + text.strip().rstrip(".") + "."}.get(mode, rules(text))
            if image is not None:
                output = output[:-1] + ", having looked at the window."
            elif screen and mode == "instruct":
                output = output[:-1] + ", having read the terminal."
            outputs = [output] + ["%s—%s" % (lead, output[0].lower() + output[1:])
                                  for lead in ("Certainly", "Of course")][:count - 1]
            usage = {}
        elif self.backend == "command":
            # An agent CLI (claude -p, ollama run, ...): the prompt goes in on stdin, never through a shell.
            if not self.lock.acquire(blocking=False):
                raise RuntimeError("the agent is still working; keep typing or retry")
            try:
                prompt = system + "\n\nText:\n" + sent
                try:
                    done = subprocess.run(self.command, input=prompt, capture_output=True, text=True,
                                          errors="replace", timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    raise RuntimeError("the agent took longer than %g s" % self.timeout)
                if done.returncode != 0:
                    raise RuntimeError("the agent failed (exit %d): %s" % (done.returncode, done.stderr.strip()[-300:]))
                outputs, usage = [done.stdout.strip()], {}
            finally:
                self.lock.release()
        elif self.claude:
            # One request at a time: no backlog of paid requests while typing.
            if not self.lock.acquire(blocking=False):
                raise RuntimeError("Claude busy; keep typing or retry")
            try:
                output, usage = self.claude.rewrite(sent, system, examples, image)
                if not output:
                    raise RuntimeError("Claude returned no text")
                outputs = [output]  # one request: alternatives would multiply the cost
            finally:
                self.lock.release()
        elif self.toolbox and mode == "instruct":
            # Agentic instruct: the model may call the profile's read-only MCP tools, then draft.
            if not self.lock.acquire(blocking=False):
                raise RuntimeError("model busy; keep typing or retry")
            try:
                def ask(messages, tools):
                    payload = {"messages": messages, "max_tokens": max_tokens, "temperature": 0, "stream": False}
                    if tools:
                        payload["tools"] = tools
                    if self.model:
                        payload["model"] = self.model
                    choice, _ = self.chat(payload, self.request_headers(), image)
                    return choice["message"]
                guide = ("\n\nYou have tools. When the instruction needs facts you do not have (status, numbers, "
                         "names, contents), call a tool first and write from its result; never invent such facts.")
                output, called, _ = self.toolbox.run(ask, [{"role": "system", "content": system + guide}] + examples +
                                                  [{"role": "user", "content": user_content(sent, image, "openai")}])
                outputs, usage, consulted = [output], {}, consulted + called
            finally:
                self.lock.release()
        else:
            # Avoid building a backlog in the model server while typing rapidly.
            if not self.lock.acquire(blocking=False):
                raise RuntimeError("model busy; keep typing or retry")
            try:
                payload = {"messages": [{"role": "system", "content": system}] + examples +
                                        [{"role": "user", "content": user_content(sent, image, "openai")}],
                           "max_tokens": max_tokens, "temperature": 0,
                           "stream": False, "cache_prompt": True}
                if self.model:
                    payload["model"] = self.model
                headers = self.request_headers()
                outputs, usage = [], {}
                for index in range(count):
                    # The first reading is deterministic (what the evaluation measures); the others
                    # are sampled, so they differ. A failed extra sample only shortens the list.
                    if index:
                        payload.update(temperature=0.9, seed=index)
                    try:
                        output, used = self.complete(payload, headers, image)
                    except Exception:
                        if index:
                            continue
                        raise
                    outputs.append(output)
                    usage = usage or used
            finally:
                self.lock.release()
        candidates = []
        from .modes import parroted
        for output in outputs:
            output = self.finish(mode, text, output)
            if parroted(mode, text, output, examples):
                continue
            if output and output not in candidates:
                candidates.append(output)
        if not candidates:
            raise RuntimeError("the model offered nothing for this %s" % mode)
        return {"text": candidates[0], "candidates": candidates, "backend": self.backend, "mode": mode,
                "consulted": consulted,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "usage": usage}
