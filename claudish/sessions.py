"""Agent sessions at the caret (G18): an instruction becomes a session with events and choices.

A driver runs the agent and reports events; the input method polls them and answers questions:
  progress  {"text"}                 what the agent is doing ("reading app.py")
  partial   {"text"}                 the draft so far
  question  {"id", "text", "choices"} a choice to make: choices are {"label", "legend"}
  result    {"text"}                 the final draft: a candidate, like any other
  error     {"text"}
A question's answer is a choice index or free text. The session ends at result, error, or cancel.
"""
import threading
import time
import uuid

MAX_SESSIONS = 4
KEEP_SECONDS = 600  # a finished session's events stay readable this long


class Session:
    def __init__(self, driver, one_line=False):
        self.id = uuid.uuid4().hex
        self.driver = driver
        self.one_line = one_line  # a terminal prompt: drafts are single lines (see screen.one_line)
        self.condition = threading.Condition()
        self.events = []
        self.questions = {}  # open question id -> number of choices
        self.done = False
        self.cancelled = False
        self.finished_at = None

    def emit(self, kind, **fields):
        with self.condition:
            if self.done:
                return
            if self.one_line and kind in ("result", "partial"):
                from .screen import one_line
                fields["text"] = one_line(fields.get("text"))
                if "candidates" in fields:
                    fields["candidates"] = [one_line(c) for c in fields["candidates"] if one_line(c)]
            event = dict(fields, seq=len(self.events), type=kind)
            self.events.append(event)
            if kind == "question":
                self.questions[event["id"]] = len(event.get("choices") or [])
            if kind in ("result", "error"):
                self.done, self.finished_at = True, time.monotonic()
            self.condition.notify_all()

    def wait(self, after=0, timeout=1.0):
        """Events with seq >= after, waiting up to timeout for the first one."""
        deadline = time.monotonic() + timeout
        with self.condition:
            while len(self.events) <= after and not self.done:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.condition.wait(remaining)
            return self.events[after:], self.done

    def answer(self, question, choice=None, text=None):
        with self.condition:
            if question not in self.questions:
                raise ValueError("no such open question")
            if text is None and not (isinstance(choice, int) and 0 <= choice < self.questions[question]):
                raise ValueError("choice out of range")
            del self.questions[question]
        self.driver.answer(question, choice, text)

    def cancel(self):
        self.cancelled = True  # before the driver stops, so its end reads as cancelled
        self.driver.cancel()
        self.emit("error", text="cancelled")


class Sessions:
    def __init__(self):
        self.lock = threading.Lock()
        self.live = {}

    def start(self, driver, prompt, one_line=False):
        with self.lock:
            now = time.monotonic()
            for key, session in list(self.live.items()):
                if session.done and now - session.finished_at > KEEP_SECONDS:
                    del self.live[key]
            if sum(not s.done for s in self.live.values()) >= MAX_SESSIONS:
                raise RuntimeError("too many agent sessions; finish or cancel one")
            session = Session(driver, one_line)
            self.live[session.id] = session
        threading.Thread(target=self.run, args=(session, prompt), daemon=True).start()
        return session

    @staticmethod
    def run(session, prompt):
        try:
            session.driver.run(session, prompt)
        except Exception as exc:  # a driver failure ends the session with an error event
            session.emit("error", text=str(exc) or type(exc).__name__)
        if not session.done:
            session.emit("error", text="cancelled" if session.cancelled else "the agent stopped without a result")

    def get(self, key):
        with self.lock:
            return self.live.get(key)
