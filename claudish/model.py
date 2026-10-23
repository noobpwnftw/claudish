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

RECENT = 8  # requests kept for `claudish recent`, for RECENT_SECONDS at most
RECENT_SECONDS = 600

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
                       settings["command"], settings["hosted"], settings["bindings"], settings.get("tone"))
        rewriter.profile = profile
        rewriter.look_command = settings.get("look_command")
        rewriter.read_terminal = settings.get("read_terminal", True)
        rewriter.helper = settings.get("helper")
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
                 context=None, modes=None, command=None, hosted=None, bindings=(), tone=None):
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
        import collections
        # The last requests, in memory only (never on disk): what was sent, to whom, and what came
        # back, for `claudish recent` (G41). Shared with routed profiles, like the sessions.
        self.recent = collections.deque(maxlen=RECENT)
        from .conversation import Conversations
        self.conversations = Conversations()  # one per text box (docs/design/instruct.md)
        self.session_command = None  # profile "session_command": a stream-json agent such as Claude Code
        self.toolbox = None  # profile "tools": read-only MCP tools an instruction may call (G17)
        self.look_command = None  # profile "look_command": argv that writes a PNG of the focused window
        self.read_terminal = True  # profile "read_terminal": a terminal's last lines go with an instruction
        self.helper = None  # profile "helper": an agent an instruction may hand the task to (G39)
        self.loader = None  # name -> Rewriter for another profile: bindings route an app to it
        self.routed = {}
        # name -> {"system", "examples", "max_tokens"}; a profile may replace any mode's template.
        custom = prompt is not None  # a --prompt rewrite template wins over a tone
        self.modes = invocation.defaults((self.system, self.examples) if custom or not tone else None, tone)
        self.modes["rewrite"]["custom"] = custom
        for name, override in (modes or {}).items():
            self.modes[name] = dict(self.modes.get(name, {"max_tokens": None}), **override)
            if "system" in override:
                self.modes[name]["custom"] = True  # a profile's own template is used as written, in any box
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

    def route(self, app, mode=None):
        """Which AI answers here: the app's binding may name a profile, and that profile may name
        another one for this mode (a small model for continue, a strong one for instructions).
        Routed profiles share this service's sessions, conversations, and recent requests."""
        chosen = self
        for binding in self.bindings:
            if binding.profile and binding.matches(app):
                chosen = self.load(binding.profile, "text typed in %s" % binding.pattern)
                break
        name = (chosen.modes.get(mode) or {}).get("profile") if mode else None
        if name and name != getattr(chosen, "profile", None):
            chosen = self.load(name, "%s requests" % mode)
        return chosen

    def load(self, name, what):
        if name == getattr(self, "profile", None) or self.loader is None:
            return self
        if name not in self.routed:
            other = self.loader(name)
            other.sessions, other.conversations, other.recent = self.sessions, self.conversations, self.recent
            other.url = getattr(self, "url", None)
            other.loader, other.routed = self.loader, self.routed  # one cache for the whole service
            self.routed[name] = other
            if other.hosted and not self.hosted:
                # A local service sending some text to a hosted model: said out loud.
                print("%s goes to profile %r, a hosted model." % (what[0].upper() + what[1:], name), flush=True)
        return self.routed[name]

    def sections(self, app=None):
        """The profile's context and the focused app's bindings (a supported text box): [(name, text)]."""
        extra = [provider for binding in self.bindings if binding.matches(app) for provider in binding.providers]
        if not (self.context or extra):
            return []
        from .context import Context
        return (self.context or Context()).sections(extra)

    def box(self, mode, app=None, purpose=None, before="", after="", look=False, screen=None, trusted=True):
        """The text box this request is for, with what its mode calls for observed. screen: a
        terminal's last lines given instead of read (tests, the terminal evaluation); trusted: False
        for the demo's requests (no token), which get nothing but their text."""
        from .turn import Box, observe
        if look:
            if mode != "instruct":
                raise ValueError("a window picture is only taken for an instruction")
            if self.backend == "command":
                raise RuntimeError("the command backend cannot take a window picture; use claude or a vision model")
        box = Box(app, "terminal" if screen else purpose, before, after)
        if trusted:
            observe(self, box, mode, look, screen)
        return box

    def make_driver(self, app=None, conversation=None, before="", after="", look=False, purpose=None, screen=None):
        """The driver for an instruction: the profile's agent (session_command), else the model
        driver, which runs it as a turn in the text box's conversation."""
        if self.session_command:
            from .agent import AgentProcess, ClaudeCodeDriver
            if not conversation:
                return ClaudeCodeDriver(self.session_command)  # a process for this turn only
            from .textbox import Textbox
            kept = self.conversations.get(conversation)
            kept.textbox = Textbox(before, after)  # what its textbox tools read this turn
            textbox = getattr(self, "url", None) and "textbox" in ((self.agent_mcp_config(kept) or {}).get("mcpServers") or {})
            kept.agent = kept.agent or AgentProcess(self.session_command + self.agent_arguments(),
                                                    self.agent_mcp_config(kept))
            # The same description of the text box a model gets, and the same observations.
            box = self.box("instruct", app, purpose, before, after, screen=screen)
            context = box.describe("instruct", retrieval=bool(textbox))
            if textbox and (box.before or box.after):
                context += " The textbox tools (read, search) see all of it."
            if box.observations:
                context += "\n\n" + box.material("").strip()
            policy = self.toolbox.policy() if self.toolbox else {}
            return ClaudeCodeDriver(self.session_command, agent=kept.agent, context=context, policy=policy)
        from .conversation import ModelDriver
        return ModelDriver(self, self.conversations.get(conversation), app, before, after, look, purpose, screen)

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
        from .turn import Box
        kind = "terminal" if screen else Box(app, purpose).kind
        return self.sessions.start(self.make_driver(app, conversation, before, after, look, purpose, screen), text,
                                   one_line=kind == "terminal")

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
        """One answer for a /suggest request (continue, rewrite, or instruct without a session).
        look: a picture of the focused window (instruct only; F8); before/after: the text box
        around the caret; purpose: the field's kind; screen: a terminal's last lines, given instead
        of read; context: False for the demo's requests (no token): no observations."""
        if mode not in self.modes:
            raise ValueError("unknown mode %r; available: %s" % (mode, ", ".join(self.modes)))
        box = self.box(mode, app, purpose, before, after, look, screen, trusted=context)
        return self.answer(mode, text, box)

    def answer(self, mode, text, box, conversation=None, approve=None, progress=None, local=None, serial=True):
        """The one loop: describe the request, call the model with the tools this mode may use, run
        tool calls (asking through approve when policy says so), and fit the result to the box.
        serial: a request while typing, which fails fast instead of queueing behind another."""
        from .modes import parroted
        from .turn import system
        started = time.perf_counter()
        spec = self.modes[mode]
        local = local or {}
        tools = mode == "instruct" and self.backend in ("llama", "openai") and bool(self.toolbox or local)
        prompt = system(spec, mode, box, retrieval=any(name.startswith("textbox__") for name in local), tools=tools)
        examples = spec["examples"] if box.prose or spec.get("custom") else []
        said = box.material(spec["frame"].replace("{text}", text) if spec.get("frame") else text)
        history = list(conversation.messages) if conversation is not None else []
        count = spec.get("candidates") or 1
        consulted, usage, new = list(box.consulted), {}, []
        from .screen import redact
        record = {"time": time.time(), "profile": getattr(self, "profile", None), "backend": self.backend,
                  "model": self.model or (self.claude.model if self.claude else None), "hosted": self.hosted,
                  "mode": mode, "app": box.app, "kind": box.kind, "system": redact(prompt)[0], "turn": redact(said)[0],
                  "examples": len(examples) // 2, "history": len(history), "picture": box.image is not None}
        self.recent.append(record)
        if serial and not self.lock.acquire(blocking=False):
            record["outcome"] = "busy"
            raise RuntimeError("the model is busy; keep typing or retry")
        try:
            if self.backend == "rules":
                outputs = self.stand_in(mode, text, box, count)
            elif self.backend == "command":
                outputs = [self.run_command(prompt + "\n\nText:\n" + said)]
            elif self.claude:
                output, usage = self.claude.rewrite(said, prompt, examples, box.image)
                if not output:
                    raise RuntimeError("Claude returned no text")
                outputs = [output]  # one request: alternatives would multiply the cost
            else:
                outputs, usage, new, called = self.ask_model(mode, prompt, examples, history, said, box, count,
                                                             tools, approve, progress, local, serial)
                consulted += called
        except Exception as exc:
            record["outcome"] = "failed: %s" % exc
            raise
        finally:
            if serial:
                self.lock.release()
        candidates = []
        for output in outputs:
            output = box.fit(mode, self.finish(mode, text, output))
            if parroted(mode, text, output, examples):
                continue
            if output and output not in candidates:
                candidates.append(output)
        if not candidates:
            raise RuntimeError("the model offered nothing for this %s" % mode)
        record.update(outcome="answered" if candidates else "nothing offered", candidates=candidates,
                      consulted=consulted, elapsed_ms=round((time.perf_counter() - started) * 1000, 1))
        if conversation is not None:
            # The conversation keeps this turn: the instruction as typed (without what was observed),
            # the tool calls and results, and the first draft.
            conversation.remember([{"role": "user", "content": text}] + new
                                  + [{"role": "assistant", "content": candidates[0]}])
        return {"text": candidates[0], "candidates": candidates, "backend": self.backend, "mode": mode,
                "profile": getattr(self, "profile", None), "hosted": self.hosted,
                "consulted": consulted,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "usage": usage}

    def ask_model(self, mode, prompt, examples, history, said, box, count, tools, approve, progress, local, serial):
        """An OpenAI-compatible server: the first answer deterministic (what the evaluation
        measures), with the tool loop when this mode has tools, then extra readings sampled over the
        same results. (outputs, usage, the turn's tool messages, what the tools consulted)."""
        from .conversation import TURN_TIMEOUT
        messages = ([{"role": "system", "content": prompt}] + examples + history
                    + [{"role": "user", "content": user_content(said, box.image, "openai")}])
        spec = self.modes[mode]
        max_tokens = spec["max_tokens"] or self.max_tokens
        usage = {}

        def ask(messages, offered, **sampling):
            nonlocal usage
            payload = {"messages": messages, "max_tokens": max_tokens, "temperature": 0, "stream": False,
                       "cache_prompt": True}
            payload.update(sampling)
            if offered:
                payload["tools"] = offered
            if self.model:
                payload["model"] = self.model
            try:
                choice, used = self.chat(payload, self.request_headers(), box.image,
                                         timeout=None if serial else max(self.timeout, TURN_TIMEOUT))
            except HTTPError:
                if not offered:
                    raise
                # A server without tool calls (an old llama.cpp without --jinja): answer without tools.
                payload.pop("tools")
                choice, used = self.chat(payload, self.request_headers(), box.image,
                                         timeout=None if serial else max(self.timeout, TURN_TIMEOUT))
            usage = usage or used
            if choice.get("finish_reason") == "length":  # never offer a sentence chopped off by the limit
                raise RuntimeError("the answer ran past its length budget; use a shorter phrase")
            return choice["message"]

        called, with_tools = [], messages
        if tools:
            from .tools import Toolbox
            first, called, with_tools = (self.toolbox or Toolbox([], {})).run(
                ask, messages, approve=approve, progress=progress, local=local)
        else:
            first = (ask(messages, None).get("content") or "").strip()
        if not first:
            raise RuntimeError("model returned no text")
        outputs = [first]
        for index in range(1, count):  # a failed extra reading only shortens the list
            try:
                more = (ask(with_tools, None, temperature=0.9, seed=index).get("content") or "").strip()
            except Exception:
                continue
            if more:
                outputs.append(more)
        return outputs, usage, with_tools[len(messages):], called

    def stand_in(self, mode, text, box, count):
        """The rules backend: deterministic answers, so the demo and tests work without a model."""
        output = {"rewrite": rules(text), "continue": "and then some—naturally.",
                  "instruct": "As requested—" + text.strip().rstrip(".") + "."}.get(mode, rules(text))
        if box.image is not None:
            output = output[:-1] + ", having looked at the window."
        elif mode == "instruct" and any(name.startswith("terminal screen") for name, _ in box.observations):
            output = output[:-1] + ", having read the terminal."
        return [output] + ["%s—%s" % (lead, output[0].lower() + output[1:])
                           for lead in ("Certainly", "Of course")][:count - 1]

    def run_command(self, prompt):
        """An agent CLI (claude -p, ollama run, ...): the prompt on stdin, never through a shell."""
        try:
            done = subprocess.run(self.command, input=prompt, capture_output=True, text=True,
                                  errors="replace", timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError("the agent took longer than %g s" % self.timeout)
        if done.returncode != 0:
            raise RuntimeError("the agent failed (exit %d): %s" % (done.returncode, done.stderr.strip()[-300:]))
        return done.stdout.strip()
