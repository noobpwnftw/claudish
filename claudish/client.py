"""A single coalescing worker: UI callbacks never wait for inference."""
import collections
import random
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

# Local typing must not be routed through HTTP_PROXY. Built once: build_opener() loads the system
# CA bundle (about 12 ms), and doing that on the worker raced OpenSSL's cleanup at process exit.
OPENER = build_opener(ProxyHandler({}))

# Runs on the background worker, never on an input event. The service enforces each backend's
# own timeout, so this only needs to outlast the slowest configured backend (agents take minutes).
def suggest(text, endpoint="http://127.0.0.1:18765", timeout=330, mode="rewrite", app=None, look=False):
    body = {"text": text, "mode": mode}
    if app:
        body["app"] = app
    if look:
        body["look"] = True
    request = Request(endpoint + "/suggest", data=json.dumps(body).encode("utf-8"),
                      headers={"Content-Type": "application/json"})
    with OPENER.open(request, timeout=timeout) as response:
        return json.load(response)


def call(endpoint, path, body=None, timeout=10):
    """A JSON request to the local service: POST with a body, else GET."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(endpoint + path, data=data, headers={"Content-Type": "application/json"})
    with OPENER.open(request, timeout=timeout) as response:
        return json.load(response)


# Agent session events, as the adapters see them (the same queue as suggestions).
EVENTS = {"progress": "progress", "partial": "partial", "question": "question"}


class Suggestions:
    def __init__(self, endpoint="http://127.0.0.1:18765", debounce=0.18):
        self.endpoint = endpoint
        self.debounce = debounce
        self.condition = threading.Condition()
        self.pending = None
        self.results = collections.deque()  # (revision, data); a session yields several
        self.closed = False
        # This text box's conversation: instructions are turns in it (docs/design/instruct.md).
        self.conversation = "%032x" % random.getrandbits(128)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def schedule(self, revision, text, mode="rewrite", immediate=False, app=None, look=False, before="", after=""):
        with self.condition:
            self.pending = (revision, text, mode, app, look, immediate, before, after,
                            time.monotonic() + (0 if immediate else self.debounce))
            self.results.clear()
            self.condition.notify()

    def poll(self):
        """The oldest unread (revision, data), or None."""
        with self.condition:
            return self.results.popleft() if self.results else None

    def answer(self, session, question, choice=None, text=None):
        """Answer an agent's question; off the input thread, so a key press never waits."""
        body = {"question": question}
        body.update({"text": text} if text is not None else {"choice": choice})

        def send():
            try:
                call(self.endpoint, "/sessions/%s/answer" % session, body, timeout=5)
            except Exception:
                pass  # the session reports its own failure
        threading.Thread(target=send, daemon=True).start()

    def close(self):
        """The text box went away: stop, and end its conversation (off the input thread)."""
        with self.condition:
            self.closed = True
            self.pending = None
            self.results.clear()
            self.condition.notify()

        def end():
            try:
                call(self.endpoint, "/conversations/%s/end" % self.conversation, {}, timeout=2)
            except Exception:
                pass
        threading.Thread(target=end, daemon=True).start()

    def deliver(self, revision, data):
        with self.condition:
            if not self.closed and self.pending is None:
                self.results.append((revision, data))
                return True
            return False

    def session(self, revision, text, app, look=False, before="", after=""):
        """Run an instruction as a turn in this text box's conversation; False if the service has
        no sessions (an older service)."""
        body = {"text": text, "conversation": self.conversation, "look": look, "before": before, "after": after}
        if app:
            body["app"] = app
        try:
            started = call(self.endpoint, "/sessions", body)
        except HTTPError as exc:
            if exc.code == 400:  # this profile has no agent: a plain instruction (about 1 ms to find out)
                return False
            raise
        key, after = started["id"], 0
        while True:
            with self.condition:
                if self.closed or self.pending is not None:  # edited, committed, or Esc: stop the agent
                    break
            data = call(self.endpoint, "/sessions/%s?after=%d" % (key, after), timeout=5)
            for event in data["events"]:
                after = event["seq"] + 1
                kind = event["type"]
                if kind == "result":
                    self.deliver(revision, {"text": event["text"], "candidates": event.get("candidates") or [event["text"]],
                                            "consulted": event.get("consulted") or [], "session": key})
                elif kind == "error":
                    self.deliver(revision, {"error": event["text"], "session": key})
                elif kind in EVENTS:
                    self.deliver(revision, {EVENTS[kind]: event if kind == "question" else event["text"],
                                            "session": key})
            if data["done"]:
                return True
        try:
            call(self.endpoint, "/sessions/%s/cancel" % key, {}, timeout=5)
        except Exception:
            pass
        return True

    def _run(self):
        while True:
            with self.condition:
                while not self.closed and self.pending is None:
                    self.condition.wait()
                if self.closed:
                    return
                revision, text, mode, app, look, immediate, before, after, due = self.pending
                remaining = due - time.monotonic()
                if remaining > 0:
                    self.condition.wait(remaining)
                    continue
                self.pending = None
            if len(text.strip()) < 3:
                continue
            try:
                # A sent instruction runs as an agent session when the profile has an agent.
                if mode == "instruct" and immediate and self.session(revision, text, app, look, before, after):
                    continue
                result = suggest(text, self.endpoint, mode=mode, app=app, look=look)
            except Exception as exc:
                result = {"error": str(exc)}
            self.deliver(revision, result)
