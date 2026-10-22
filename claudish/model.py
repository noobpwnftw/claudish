import base64
import json
import os
import re
import subprocess
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
        self.look_command = None  # profile "look_command": argv that writes a PNG of the focused window
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

    def rewrite(self, text, before="", after="", mode="rewrite", app=None, look=False):
        """look: attach a picture of the focused window (instruct only; the user asked for it with F8)."""
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
        spec = self.modes[mode]
        # A supported text box: bindings for the focused app add their context providers.
        extra = [provider for binding in self.bindings if binding.matches(app) for provider in binding.providers]
        if self.context or extra:
            from .context import Context
            block, consulted = (self.context or Context()).gather(before, after, extra)
        else:
            block, consulted = "", []
        if image is not None:
            consulted = consulted + ["window picture (%d×%d)" % (width, height)]
        system = spec["system"] + block
        examples, max_tokens = spec["examples"], spec["max_tokens"] or self.max_tokens
        if self.backend == "rules":
            # Deterministic stand-ins so the demo and tests work without a model.
            output = {"rewrite": rules(text), "continue": "and then some—naturally.",
                      "instruct": "As requested—" + text.strip().rstrip(".") + "."}.get(mode, rules(text))
            if image is not None:
                output = output[:-1] + ", having looked at the window."
            usage = {}
        elif self.backend == "command":
            # An agent CLI (claude -p, ollama run, ...): the prompt goes in on stdin, never through a shell.
            if not self.lock.acquire(blocking=False):
                raise RuntimeError("the agent is still working; keep typing or retry")
            try:
                prompt = system + "\n\nText:\n" + text
                try:
                    done = subprocess.run(self.command, input=prompt, capture_output=True, text=True,
                                          errors="replace", timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    raise RuntimeError("the agent took longer than %g s" % self.timeout)
                if done.returncode != 0:
                    raise RuntimeError("the agent failed (exit %d): %s" % (done.returncode, done.stderr.strip()[-300:]))
                output, usage = done.stdout.strip(), {}
            finally:
                self.lock.release()
        elif self.claude:
            # One request at a time: no backlog of paid requests while typing.
            if not self.lock.acquire(blocking=False):
                raise RuntimeError("Claude busy; keep typing or retry")
            try:
                output, usage = self.claude.rewrite(text, system, examples, image)
                if not output:
                    raise RuntimeError("Claude returned no text")
            finally:
                self.lock.release()
        else:
            # Avoid building a backlog in the model server while typing rapidly.
            if not self.lock.acquire(blocking=False):
                raise RuntimeError("model busy; keep typing or retry")
            try:
                payload = {"messages": [{"role": "system", "content": system}] + examples +
                                        [{"role": "user", "content": user_content(text, image, "openai")}],
                           "max_tokens": max_tokens, "temperature": 0,
                           "stream": False, "cache_prompt": True}
                if self.model:
                    payload["model"] = self.model
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["Authorization"] = "Bearer " + self.api_key
                req = Request(self.endpoint + "/v1/chat/completions",
                              data=json.dumps(payload).encode(), headers=headers)
                # Loopback traffic must not go through HTTP_PROXY; a remote endpoint may need it.
                # Built once: build_opener() loads the system CA bundle, about 12 ms per call.
                if self.opener is None:
                    self.opener = build_opener(ProxyHandler({})) if self.local else build_opener()
                try:
                    with self.opener.open(req, timeout=self.timeout) as response:
                        data = json.load(response)
                except HTTPError as exc:
                    if image is not None and exc.code in (400, 500, 501):
                        raise RuntimeError("this model server did not accept the window picture; it needs a vision "
                                           "model (llama.cpp: --mmproj)") from exc
                    raise
                choice = data["choices"][0]
                # Never offer a sentence chopped off by the token limit.
                if choice.get("finish_reason") == "length":
                    raise RuntimeError("rewrite exceeded token budget; use a shorter phrase")
                output = choice["message"]["content"].strip()
                usage = data.get("usage", {})
                if not output:
                    raise RuntimeError("model returned no text")
            finally:
                self.lock.release()
        output = self.finish(mode, text, output)
        if not output:
            raise RuntimeError("the model offered nothing for this %s" % mode)
        return {"text": output, "backend": self.backend, "mode": mode, "consulted": consulted,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "usage": usage}
