import json
import sys
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from claudish.model import Rewriter
from claudish.server import make_server
from claudish.sessions import Session

AGENT = [sys.executable, str(Path(__file__).with_name("fake_agent.py"))]


class ServiceTests(unittest.TestCase):
    """The session API over HTTP, with a scripted agent speaking Claude Code's stream-json protocol."""

    def setUp(self):
        self.rewriter = Rewriter("rules")
        self.rewriter.session_command = AGENT
        self.server = make_server(self.rewriter, 0)
        thread = threading.Thread(target=self.server.serve_forever)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.opener = build_opener(ProxyHandler({}))

    def call(self, path, body=None):
        url = "http://127.0.0.1:%d%s" % (self.server.server_port, path)
        request = Request(url, json.dumps(body).encode() if body is not None else None,
                          {"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def until(self, session, kind, after=0, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _, data = self.call("/sessions/%s?after=%d" % (session, after))
            for event in data["events"]:
                if event["type"] == kind:
                    return event
                if event["type"] == "error" and kind != "error":
                    self.fail("session failed: %s" % event)
            after += len(data["events"])
        self.fail("no %s event" % kind)

    def test_a_question_becomes_choices_and_the_answer_reaches_the_agent(self):
        status, data = self.call("/sessions", {"text": "is my branch clean?"})
        self.assertEqual(status, 200, data)
        session = data["id"]
        partial = self.until(session, "partial")
        self.assertTrue(partial["text"].startswith("Checking"))
        question = self.until(session, "question")
        self.assertEqual([c["label"] for c in question["choices"]], ["Allow", "Deny"])
        self.assertEqual(question["choices"][0]["legend"], "Show the working tree status")
        self.assertEqual(self.call("/sessions/%s/answer" % session, {"question": question["id"], "choice": 5})[0], 400)
        self.assertEqual(self.call("/sessions/%s/answer" % session, {"question": question["id"], "choice": 0})[0], 200)
        result = self.until(session, "result")
        self.assertEqual(result["text"], "The branch is clean—nothing to commit.")
        _, data = self.call("/sessions/%s?after=0" % session)
        self.assertTrue(data["done"])
        self.assertIn("Bash: git status", [e["text"] for e in data["events"] if e["type"] == "progress"])

    def test_free_text_is_a_denial_with_your_words(self):
        _, data = self.call("/sessions", {"text": "is my branch clean?"})
        question = self.until(data["id"], "question")
        self.call("/sessions/%s/answer" % data["id"], {"question": question["id"], "text": "use git diff instead"})
        self.assertEqual(self.until(data["id"], "result")["text"],
                         "Understood—I left it alone. (use git diff instead)")

    def test_cancel_stops_the_agent(self):
        _, data = self.call("/sessions", {"text": "slow task"})
        session = self.rewriter.sessions.get(data["id"])
        for _ in range(50):
            if session.driver.process is not None:
                break
            time.sleep(0.05)
        self.assertEqual(self.call("/sessions/%s/cancel" % data["id"], {})[0], 200)
        self.assertEqual(self.until(data["id"], "error")["text"], "cancelled")
        session.driver.process.wait(timeout=5)  # killed, not left running

    def test_requests_are_checked(self):
        self.assertEqual(self.call("/sessions", {"text": ""})[0], 400)
        self.assertEqual(self.call("/sessions/nope?after=0")[0], 404)
        rewriter = Rewriter("rules")  # no agent: the model driver runs the instruction
        session = rewriter.start_session("hi")
        events, done = session.wait(0, timeout=5)
        self.assertTrue(done)
        self.assertEqual(events[-1]["type"], "result")
        self.assertEqual(events[-1]["candidates"][0], "As requested—hi.")


class SessionTests(unittest.TestCase):
    def test_no_events_after_the_end_and_answers_are_validated(self):
        class Quiet:
            def answer(self, *args):
                self.answered = args

            def cancel(self):
                pass
        session = Session(Quiet())
        session.emit("question", id="q", text="Allow?", choices=[{"label": "Allow"}, {"label": "Deny"}])
        with self.assertRaises(ValueError):
            session.answer("other", 0)
        session.answer("q", 1)
        self.assertEqual(session.driver.answered, ("q", 1, None))
        with self.assertRaises(ValueError):
            session.answer("q", 0)  # answered already
        session.emit("result", text="done")
        session.emit("progress", text="late")
        events, done = session.wait(0, 0)
        self.assertEqual(([e["type"] for e in events], done), (["question", "result"], True))


if __name__ == "__main__":
    unittest.main()
