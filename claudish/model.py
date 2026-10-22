import json
import re
import threading
import time
from urllib.parse import urlsplit
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


class Claude:
    """Opt-in hosted backend: typed text is sent to the Anthropic API."""

    def __init__(self, model):
        import anthropic  # Optional dependency: pip install "claudish-ime[claude]"
        # Credentials come from ANTHROPIC_API_KEY or an `ant auth login` profile.
        # A stale suggestion is useless, so fail fast instead of retrying.
        self.client = anthropic.Anthropic(timeout=10.0, max_retries=0)
        self.model = model

    def rewrite(self, text, system, examples):
        options = {}
        if not self.model.startswith("claude-haiku"):  # Haiku has no server-side fallback.
            options = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            response = self.client.beta.messages.create(
                model=self.model, max_tokens=2048, system=system,
                messages=examples + [{"role": "user", "content": text}],
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

    def __init__(self, backend="llama", endpoint="http://127.0.0.1:18766", max_tokens=64,
                 claude_model="claude-opus-5-5", model=None, api_key=None, timeout=3, prompt=None):
        self.backend = backend
        self.endpoint = endpoint.rstrip("/")
        self.max_tokens = max_tokens
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.system, self.examples = prompt or (SYSTEM, EXAMPLES)
        self.lock = threading.Lock()
        self.local = urlsplit(self.endpoint).hostname in ("127.0.0.1", "localhost", "::1")
        self.hosted = backend == "claude" or (backend in ("llama", "openai") and not self.local)
        self.claude = Claude(claude_model) if backend == "claude" else None

    def rewrite(self, text):
        started = time.perf_counter()
        if self.backend == "rules":
            output = rules(text)
            usage = {}
        elif self.claude:
            # One request at a time: no backlog of paid requests while typing.
            if not self.lock.acquire(blocking=False):
                raise RuntimeError("Claude busy; keep typing or retry")
            try:
                output, usage = self.claude.rewrite(text, self.system, self.examples)
                if not output:
                    raise RuntimeError("Claude returned no text")
            finally:
                self.lock.release()
        else:
            # Avoid building a backlog in the model server while typing rapidly.
            if not self.lock.acquire(blocking=False):
                raise RuntimeError("model busy; keep typing or retry")
            try:
                payload = {"messages": [{"role": "system", "content": self.system}] + self.examples +
                                        [{"role": "user", "content": text}],
                           "max_tokens": self.max_tokens, "temperature": 0,
                           "stream": False, "cache_prompt": True}
                if self.model:
                    payload["model"] = self.model
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["Authorization"] = "Bearer " + self.api_key
                req = Request(self.endpoint + "/v1/chat/completions",
                              data=json.dumps(payload).encode(), headers=headers)
                # Loopback traffic must not go through HTTP_PROXY; a remote endpoint may need it.
                opener = build_opener(ProxyHandler({})) if self.local else build_opener()
                with opener.open(req, timeout=self.timeout) as response:
                    data = json.load(response)
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
        return {"text": output, "backend": self.backend,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "usage": usage}
