"""A single coalescing worker: UI callbacks never wait for inference."""
import collections
import os
import random
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

# Local typing must not be routed through HTTP_PROXY. Built once: build_opener() loads the system
# CA bundle (about 12 ms), and doing that on the worker raced OpenSSL's cleanup at process exit.
OPENER = build_opener(ProxyHandler({}))
# An input method starts with the login, as the service does: until this process first reaches the
# service, a refused connection in its first minute is the service still starting ("initializing").
STARTED = time.monotonic()
STARTING_SECONDS = 60
REACHED = threading.Event()

def token_path():
    """The service's token: written by the service at start and sent by the input methods."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "claudish", "service-token")


def read_token():
    try:
        with open(token_path()) as source:
            return source.read().strip()
    except OSError:
        return ""


def write_private(path, text):
    """Replace path with text: a fresh temporary file, then a rename."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    temporary = str(path) + ".tmp"
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as out:
        if hasattr(os, "fchmod"):
            os.fchmod(out.fileno(), 0o600)  # whatever the umask
        out.write(text)
    os.replace(temporary, path)


def write_token(token=None):
    """This service run's token (a new one when None), in its file."""
    import secrets
    token = token or secrets.token_urlsafe(32)
    write_private(token_path(), token)
    return token


def settings_url(url="http://127.0.0.1:18765"):
    """The settings page of a running service, with a ticket in the fragment, which the page
    trades for its settings token. OSError when no service answers."""
    request = Request(url.rstrip("/") + "/settings/ticket", data=b"{}", headers=headers())
    with OPENER.open(request, timeout=10) as response:  # a service just started at login is slow at first
        ticket = json.load(response)["ticket"]
    return "%s/settings#ticket=%s" % (url.rstrip("/"), ticket)


def headers():
    sent = {"Content-Type": "application/json"}
    token = read_token()
    if token:
        sent["X-Claudish-Token"] = token
    return sent


# Runs on the background worker, never on an input event. The service enforces each backend's
# own timeout, so this only needs to outlast the slowest configured backend (agents take minutes).
def suggest(text, endpoint="http://127.0.0.1:18765", timeout=330, mode="rewrite", app=None, look=False,
            before="", after="", purpose=None):
    """before/after: the text box around the caret (where the result goes); purpose: the field's
    kind as the input method reports it ("terminal", "email", ...)."""
    body = {"text": text, "mode": mode}
    for key, value in (("app", app), ("look", look), ("before", before), ("after", after), ("purpose", purpose)):
        if value:
            body[key] = value
    request = Request(endpoint + "/suggest", data=json.dumps(body).encode("utf-8"), headers=headers())
    with OPENER.open(request, timeout=timeout) as response:
        return json.load(response)


def call(endpoint, path, body=None, timeout=10):
    """A JSON request to the local service: POST with a body, else GET."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(endpoint + path, data=data, headers=headers())
    with OPENER.open(request, timeout=timeout) as response:
        return json.load(response)


class Suggestions:
    def __init__(self, endpoint="http://127.0.0.1:18765", debounce=0.18):
        self.endpoint = endpoint
        self.debounce = debounce
        self.condition = threading.Condition()
        self.pending = None
        self.results = collections.deque()  # (revision, data); a session yields several
        self.closed = False
        # This text box's conversation: instructions are turns in it (docs/design/architecture.md).
        self.conversation = "%032x" % random.getrandbits(128)
        self.offline = False  # the service did not answer its last check: True, or "initializing"
        self.revisions = {}  # an agent session's id -> the instruction's revision (its answers' errors go there)
        # The revisions the composition still shows (Composition.follow sets them): the current one and
        # a held exchange's. A session for another one is over for the person: it is cancelled.
        self.wanted = None
        self.summon = "Shift+Enter"  # the key that sends your words to the model (the config's "keys")
        self.hints = True  # the config's "hints"
        self.stopped = threading.Event()  # its own: a notify on the condition must wake the requests
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self, every=3.0):
        """Whether the service answers, checked off the input thread every few seconds, so the panel
        says it is offline from the first key (a refused connection on this computer fails at once)."""
        missed = 0
        while True:
            try:
                with OPENER.open(self.endpoint + "/health", timeout=2) as answer:
                    self.offline, missed = False, 0
                    REACHED.set()
                    try:  # the config's keys, taken up as the service takes up a hand edit
                        health = json.loads(answer.read().decode("utf-8"))
                        self.summon = health["keys"]["summon"]
                        self.hints = health.get("hints", True) is not False
                    except (ValueError, KeyError, TypeError):
                        pass
            except Exception as exc:
                missed += 1
                # Nothing listening is offline at once; a slow answer (a busy machine, a settings
                # reload) only when it happens twice in a row.
                refused = isinstance(getattr(exc, "reason", exc), ConnectionRefusedError)
                if refused or missed >= 2:
                    starting = not REACHED.is_set() and time.monotonic() - STARTED < STARTING_SECONDS
                    self.offline = "initializing" if starting else True
            if self.stopped.wait(every):
                return

    def schedule(self, revision, text, mode="rewrite", immediate=False, app=None, look=False, before="", after="",
                 purpose=None, draft=""):
        """draft: a follow-up's draft, the one in view and not yet in the text (Composition.about)."""
        with self.condition:
            self.pending = (revision, text, mode, app, look, immediate, before, after, purpose, draft,
                            time.monotonic() + (0 if immediate else self.debounce))
            # A newer request makes earlier suggestions stale; an agent session's events stay.
            kept = [result for result in self.results if "session" in result[1]]
            self.results.clear()
            self.results.extend(kept)
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
            error = "the answer did not reach cd_AI's service"
            for attempt in range(3):
                try:
                    call(self.endpoint, "/sessions/%s/answer" % session, body, timeout=5)
                    return
                except HTTPError as exc:
                    if exc.code < 500:  # the service has no such open question: the instruction is over
                        error = "the instruction had ended (no answer in time, or it was stopped)"
                        break
                    time.sleep(0.5)
                except Exception:
                    time.sleep(0.5)
            # The service never took it: the session ends, and the instruction says so (the summon
            # key asks again), whatever else is pending.
            self._cancel(session)
            revision = self.revisions.get(session)
            if revision is not None:
                self.deliver(revision, {"error": error, "session": session}, always=True)
        threading.Thread(target=send, daemon=True).start()

    def new_conversation(self, end=True):
        """Another text box behind the same input method instance (Windows runs one per app thread):
        a fresh conversation, the old one ended unless an exchange held from it goes on (end=False:
        the service ends it after its idle period)."""
        old, self.conversation = self.conversation, "%032x" % random.getrandbits(128)
        if end:
            threading.Thread(target=lambda: self._end(old), daemon=True).start()

    def _end(self, conversation):
        try:
            call(self.endpoint, "/conversations/%s/end" % conversation, {}, timeout=2)
        except Exception:
            pass

    def close(self):
        """The text box went away: stop, and end its conversation (off the input thread)."""
        self.stopped.set()
        with self.condition:
            self.closed = True
            self.pending = None
            self.results.clear()
            self.condition.notify()
        threading.Thread(target=self._end, args=(self.conversation,), daemon=True).start()

    def deliver(self, revision, data, always=False):
        """A result for the composition. A newer request drops a plain one; an agent session's
        events go through (always), tagged with their revision: the composition takes them for its
        current exchange or a held one, and ignores the rest."""
        with self.condition:
            if not self.closed and (always or self.pending is None):
                self.results.append((revision, data))
                return True
            return False

    def session(self, revision, text, app, look=False, before="", after="", purpose=None, draft=""):
        """Run an instruction as a turn in this text box's conversation (an HTTPError says why the
        service refused it)."""
        body = {"text": text, "conversation": self.conversation, "look": look, "before": before, "after": after}
        if purpose:
            body["purpose"] = purpose
        if app:
            body["app"] = app
        if draft:
            body["draft"] = draft
        key = call(self.endpoint, "/sessions", body)["id"]
        with self.condition:
            # Wanted from the start: a follow-up's revision is new at Shift+Enter, and the adapter's
            # next poll (Composition.follow) may come after the follower's first look, which would
            # cancel the session it just started.
            if self.wanted is not None:
                self.wanted = set(self.wanted) | {revision}
        self.revisions[key] = revision  # an answer that cannot be sent fails this instruction
        for old in list(self.revisions)[:-16]:  # the last few sessions' answers can still fail
            del self.revisions[old]
        # Followed beside the requests: a held exchange's agent goes on while continue suggests.
        threading.Thread(target=self._follow_session, args=(revision, key), daemon=True).start()

    def _follow_session(self, revision, key):
        try:
            self._follow(revision, key)
        except Exception as exc:
            self.deliver(revision, {"error": str(exc), "session": key}, always=True)

    def _follow(self, revision, key):
        after, missed = 0, 0
        while True:
            with self.condition:
                if self.closed or (self.wanted is not None and revision not in self.wanted):
                    break  # edited, committed, Esc, or a new instruction: the agent stops
            try:
                data = call(self.endpoint, "/sessions/%s?after=%d" % (key, after), timeout=5)
                missed = 0
            except Exception:
                # A busy service can miss a poll: ask again. When it keeps failing, the session is
                # cancelled before the error goes up, so a retry does not run beside it.
                missed += 1
                if missed < 3:
                    time.sleep(0.5)
                    continue
                self._cancel(key)
                raise
            for event in data["events"]:
                after = event["seq"] + 1
                kind = event["type"]
                if kind == "result" and event.get("done"):
                    self.deliver(revision, {"done": event["done"], "session": key}, always=True)
                elif kind == "result":
                    self.deliver(revision, {"text": event["text"], "candidates": event.get("candidates") or [event["text"]],
                                            "session": key}, always=True)
                elif kind == "error":
                    self.deliver(revision, {"error": event["text"], "session": key}, always=True)
                elif kind in ("progress", "partial", "question"):  # as the adapters see them, beside suggestions
                    self.deliver(revision, {kind: event if kind == "question" else event["text"], "session": key},
                                 always=True)
            if data["done"]:
                return True
        self._cancel(key)
        return True

    def _cancel(self, key):
        try:
            call(self.endpoint, "/sessions/%s/cancel" % key, {}, timeout=5)
        except Exception:
            pass

    def _run(self):
        while True:
            with self.condition:
                while not self.closed and self.pending is None:
                    self.condition.wait()
                if self.closed:
                    return
                revision, text, mode, app, look, immediate, before, after, purpose, draft, due = self.pending
                remaining = due - time.monotonic()
                if remaining > 0:
                    self.condition.wait(remaining)
                    continue
                self.pending = None
            if not text.strip() or (mode == "continue" and len(text.strip()) < 3):
                continue  # continue asks by itself at every pause, so not for a word or two; Tab asks for anything
            try:
                # A sent instruction runs as a turn of this text box's conversation (a session).
                if mode == "instruct" and immediate:
                    self.session(revision, text, app, look, before, after, purpose, draft)
                    continue
                result = suggest(text, self.endpoint, mode=mode, app=app, look=look, before=before, after=after,
                                 purpose=purpose)
            except HTTPError as exc:
                # The service explains model failures in JSON; the HTTP status alone loses why
                # (for example, a missing key becomes only "503 Service Unavailable").
                try:
                    with exc:
                        detail = json.loads(exc.read(32768))
                    message = detail.get("error") if isinstance(detail, dict) else None
                except (ValueError, OSError):
                    message = None
                result = {"error": message if isinstance(message, str) and message else str(exc)}
            except Exception as exc:
                result = {"error": str(exc)}
            self.deliver(revision, result)
