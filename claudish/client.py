"""A single coalescing worker: UI callbacks never wait for inference."""
import json
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler


# Runs on the background worker, never on an input event, so a hosted backend may take longer.
def suggest(text, endpoint="http://127.0.0.1:18765", timeout=12, mode="rewrite"):
    request = Request(endpoint + "/suggest", data=json.dumps({"text": text, "mode": mode}).encode("utf-8"),
                      headers={"Content-Type": "application/json"})
    # Local typing must not be routed through HTTP_PROXY.
    with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.load(response)


class Suggestions:
    def __init__(self, endpoint="http://127.0.0.1:18765", debounce=0.18):
        self.endpoint = endpoint
        self.debounce = debounce
        self.condition = threading.Condition()
        self.pending = None
        self.result = None
        self.closed = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def schedule(self, revision, text, mode="rewrite"):
        with self.condition:
            self.pending = (revision, text, mode, time.monotonic() + self.debounce)
            self.result = None
            self.condition.notify()

    def poll(self):
        with self.condition:
            result, self.result = self.result, None
            return result

    def close(self):
        with self.condition:
            self.closed = True
            self.pending = None
            self.result = None
            self.condition.notify()

    def _run(self):
        while True:
            with self.condition:
                while not self.closed and self.pending is None:
                    self.condition.wait()
                if self.closed:
                    return
                revision, text, mode, due = self.pending
                remaining = due - time.monotonic()
                if remaining > 0:
                    self.condition.wait(remaining)
                    continue
                self.pending = None
            if len(text.strip()) < 3:
                continue
            try:
                result = suggest(text, self.endpoint, mode=mode)
            except Exception as exc:
                result = {"error": str(exc)}
            with self.condition:
                if not self.closed and self.pending is None:
                    self.result = (revision, result)
