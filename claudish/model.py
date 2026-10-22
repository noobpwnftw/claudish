import json
import re
import threading
import time
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


class Rewriter:
    def __init__(self, backend="llama", endpoint="http://127.0.0.1:18766", max_tokens=64):
        self.backend = backend
        self.endpoint = endpoint
        self.max_tokens = max_tokens
        self.lock = threading.Lock()

    def rewrite(self, text):
        started = time.perf_counter()
        if self.backend == "rules":
            output = rules(text)
            usage = {}
        else:
            # Avoid building a backlog in the model server while typing rapidly.
            if not self.lock.acquire(blocking=False):
                raise RuntimeError("model busy; keep typing or retry")
            try:
                payload = {"messages": [{"role": "system", "content": SYSTEM}] + EXAMPLES +
                                        [{"role": "user", "content": text}],
                           "max_tokens": self.max_tokens, "temperature": 0,
                           "stream": False, "cache_prompt": True}
                req = Request(self.endpoint + "/v1/chat/completions",
                              data=json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"})
                with build_opener(ProxyHandler({})).open(req, timeout=3) as response:
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
