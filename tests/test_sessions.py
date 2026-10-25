import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
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
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.rewriter.conversations.close)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.opener = build_opener(ProxyHandler({}))

    def call(self, path, body=None):
        url = "http://127.0.0.1:%d%s" % (self.server.server_port, path)
        request = Request(url, json.dumps(body).encode() if body is not None else None,
                          {"Content-Type": "application/json", "X-Claudish-Token": self.server.token})
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
        self.assertEqual([c["label"] for c in question["choices"]], ["Deny", "Allow"])  # the safe choice first
        self.assertEqual((question["label"], question["body"], question["code"]),
                         ("Claude Code wants to run", "git status", True))
        self.assertEqual(self.call("/sessions/%s/answer" % session, {"question": question["id"], "choice": 5})[0], 400)
        self.assertEqual(self.call("/sessions/%s/answer" % session, {"question": question["id"], "choice": 1})[0], 200)
        result = self.until(session, "result")
        self.assertEqual(result["text"], "The branch is clean—nothing to commit.")
        _, data = self.call("/sessions/%s?after=0" % session)
        self.assertTrue(data["done"])
        self.assertIn("Bash: git status", [e["text"] for e in data["events"] if e["type"] == "progress"])

    def test_the_agents_own_questions_are_shown_as_is(self):
        """Claude Code's AskUserQuestion is the agent asking (ask), not a permission to grant:
        each question is shown with its options, and the answers go back keyed by the question."""
        _, data = self.call("/sessions", {"text": "pick a colour"})
        first = self.until(data["id"], "question")
        self.assertEqual(first["text"], "Which colour?")
        self.assertEqual([(c["label"], c["legend"]) for c in first["choices"]], [("Red", "warm"), ("Blue", "cool")])
        self.assertEqual(self.call("/sessions/%s/answer" % data["id"], {"question": first["id"], "choice": 1})[0], 200)
        second = self.until(data["id"], "question", after=first["seq"] + 1)
        self.assertEqual(second["text"], "Which shade?")
        self.call("/sessions/%s/answer" % data["id"], {"question": second["id"], "text": "teal-ish"})  # your own words
        self.assertEqual(self.until(data["id"], "result")["text"], "Blue, teal-ish")

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

    def turn(self, text, conversation="box"):
        _, data = self.call("/sessions", {"text": text, "conversation": conversation})
        return data["id"]

    def test_a_conversation_keeps_its_agent_between_turns(self):
        first = self.until(self.turn("count"), "result")["text"]
        self.assertRegex(first, r"^turn 1 of this process \(--session-id [0-9a-f-]{36}\)$")
        self.assertEqual(self.until(self.turn("count"), "result")["text"], first.replace("turn 1", "turn 2"))
        self.assertTrue(self.until(self.turn("count", "other"), "result")["text"].startswith("turn 1 "))
        agent = self.rewriter.conversations.get("box").agent
        process = agent.process
        self.assertEqual(self.call("/conversations/box/end", {})[0], 200)
        process.wait(timeout=5)  # the conversation ended: its agent exits
        self.assertIsNone(self.rewriter.conversations.get("box").agent)

    def test_esc_interrupts_the_turn_and_keeps_the_agent(self):
        session = self.turn("slow task")
        agent = None
        for _ in range(50):
            agent = self.rewriter.conversations.get("box").agent
            if agent is not None and agent.running:
                break
            time.sleep(0.05)
        process = agent.process
        self.assertEqual(self.call("/sessions/%s/cancel" % session, {})[0], 200)
        self.assertEqual(self.until(session, "error")["text"], "cancelled")
        self.assertRegex(self.until(self.turn("count"), "result")["text"], r"^turn 2 ")
        self.assertIs(agent.process, process)

    def test_an_agent_that_exited_is_resumed_by_session_id(self):
        self.until(self.turn("count"), "result")
        agent = self.rewriter.conversations.get("box").agent
        agent.process.kill()
        agent.process.wait()
        text = self.until(self.turn("count"), "result")["text"]
        self.assertEqual(text, "turn 1 of this process (--resume %s)" % agent.session_id)

    def test_the_agent_reads_the_text_box_over_mcp(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest('needs the MCP SDK: pip install "claudish-ime[mcp]"')
        before = "Minutes. The budget for Q3 is 40k.\n" + "Filler.\n" * 400
        _, data = self.call("/sessions", {"text": "use the textbox", "conversation": "box", "before": before})
        result = self.until(data["id"], "result", timeout=30)["text"]
        names, found, caret = result.split(" | ")
        self.assertEqual(names, "read,search")
        self.assertIn("The budget for Q3 is 40k", found)
        self.assertEqual(caret, "caret seen: True")
        self.assertEqual([e for e in self.call("/sessions/%s?after=0" % data["id"])[1]["events"]
                          if e["type"] == "question"], [])  # the read ran by policy, unasked
        # Without the conversation's token, the text box is not readable.
        self.assertEqual(self.call("/conversations/box/textbox", {"op": "read"})[0], 404)
        config = self.rewriter.conversations.get("box").agent.config_file
        self.call("/conversations/box/end", {})
        self.assertFalse(Path(config).exists())  # the token's file goes with the conversation

    def test_an_agent_gets_the_profiles_servers_context_and_policy(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest('needs the MCP SDK: pip install "claudish-ime[mcp]"')
        from claudish.context import Context
        from claudish.tools import Toolbox
        servers = {"notes": {"command": sys.executable, "args": [str(Path(__file__).with_name("mcp_server.py"))]}}
        self.rewriter.toolbox = Toolbox([{"server": "notes", "trust": ["ci_status"], "deny": ["delete_branch"]}], servers)
        self.rewriter.context = Context([{"type": "command", "name": "notes", "command": ["echo", "PROJECT-NOTES"]}])
        result = self.until(self.turn("policy"), "result", timeout=30)["text"]
        # The profile's servers as configured for Claudish, plus the text box; a denied tool is never
        # offered, a trusted one runs unasked, and the profile's context goes with the turn.
        self.assertEqual(result, "servers=notes,textbox disallowed=mcp__notes__delete_branch answers=allow,deny context=True")

    def test_only_an_input_method_with_the_token_drives_sessions_or_reads_the_text_box(self):
        """Any local process can reach the port; only the input methods can read the token file."""
        url = "http://127.0.0.1:%d" % self.server.server_port

        def anonymous(path, body=None):
            request = Request(url + path, json.dumps(body).encode() if body is not None else None,
                              {"Content-Type": "application/json"})
            try:
                with self.opener.open(request, timeout=10) as response:
                    return response.status
            except HTTPError as error:
                return error.code
        self.assertEqual(anonymous("/sessions", {"text": "hi"}), 403)
        self.assertEqual(anonymous("/sessions/x/answer", {"question": "q", "choice": 0}), 403)
        self.assertEqual(anonymous("/sessions/x?after=0"), 403)
        self.assertEqual(anonymous("/conversations/x/end", {}), 403)
        # The demo's request (text and a mode) works; what is around the caret, the app (which can
        # mean reading a terminal), and window pictures do not.
        self.assertEqual(anonymous("/suggest", {"text": "very good", "mode": "rewrite"}), 200)
        for extra in ({"app": "gnome-terminal-server"}, {"before": "Dear Ana"}, {"purpose": "terminal"},
                      {"look": True, "mode": "instruct"}):
            self.assertEqual(anonymous("/suggest", dict({"text": "fix", "mode": "rewrite"}, **extra)), 403, extra)

    def test_recent_requests_show_what_was_sent_only_with_the_token(self):
        url = "http://127.0.0.1:%d" % self.server.server_port
        self.rewriter.rewrite("very important", before="Dear Ana, ", app="thunderbird")
        with self.assertRaises(HTTPError) as error:
            self.opener.open(Request(url + "/recent"), timeout=5)
        self.assertEqual(error.exception.code, 403)  # typed text: not for any local process
        status, data = self.call("/recent")
        self.assertEqual(status, 200)
        item = data["recent"][-1]
        self.assertEqual((item["mode"], item["app"], item["backend"], item["outcome"]),
                         ("rewrite", "thunderbird", "rules", "answered"))
        self.assertIn("Dear Ana, ▮", item["system"])
        self.assertEqual(item["turn"], "very important")
        self.assertEqual(item["candidates"], ["particularly crucial"])
        self.assertEqual(self.call("/recent/clear", {})[0], 200)
        self.assertEqual(self.call("/recent")[1]["recent"], [])
        # A password field is never sent, whatever an adapter does.
        self.assertEqual(self.call("/suggest", {"text": "hunter2", "purpose": "password"})[0], 400)

    def test_the_token_file_is_private_and_new_for_each_run(self):
        import os
        import tempfile
        from claudish import client
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"XDG_CONFIG_HOME": home}):
            first = client.write_token()
            self.assertEqual(client.read_token(), first)
            self.assertEqual(client.headers()["X-Claudish-Token"], first)
            if os.name == "posix":
                self.assertEqual(os.stat(client.token_path()).st_mode & 0o777, 0o600)
            self.assertNotEqual(client.write_token(), first)

    def test_requests_are_checked(self):
        self.assertEqual(self.call("/sessions", {"text": ""})[0], 400)
        self.assertEqual(self.call("/sessions/nope?after=0")[0], 404)
        rewriter = Rewriter("rules")  # no agent: the model driver runs the instruction
        session = rewriter.start_session("hi")
        events, done = session.wait(0, timeout=5)
        self.assertTrue(done)
        self.assertEqual(events[-1]["type"], "result")
        self.assertEqual(events[-1]["candidates"][0], "As requested—hi.")


class BindTests(unittest.TestCase):
    def test_the_service_binds_without_a_name_lookup(self):
        # socket.getfqdn can go out over multicast DNS on macOS: the Local Network privacy prompt.
        from unittest.mock import patch
        with patch("socket.getfqdn", side_effect=AssertionError("name lookup")):
            server = make_server(Rewriter("rules"), 0)
        server.server_close()
        self.assertEqual(server.server_name, "localhost")


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



class AnswerTests(unittest.TestCase):
    def test_the_same_answer_again_is_taken_once(self):
        """Codex: an answer the service took, whose reply was lost, came again; the service said
        "no such open question" and the client cancelled a working task."""
        class Driver:
            answers = []

            def run(self, session, text):
                pass

            def answer(self, question, choice, text):
                self.answers.append((question, choice, text))

            def cancel(self):
                pass
        driver = Driver()
        session = Session(driver)
        session.emit("question", id="q1", text="Allow?", choices=[{"label": "Deny"}, {"label": "Allow"}])
        session.answer("q1", choice=1)
        session.answer("q1", choice=1)  # the retry: fine, and not run twice
        self.assertEqual(driver.answers, [("q1", 1, None)])
        with self.assertRaises(ValueError):
            session.answer("q1", choice=0)  # a different answer to an answered question is refused


class RoutingTests(unittest.TestCase):
    def test_two_requests_at_once_load_a_profile_once(self):
        """Codex: two requests for a routed profile at once started two backends; one leaked."""
        import threading
        import time
        from claudish.model import Rewriter
        started = []

        def loader(name):
            time.sleep(0.05)  # both requests are in here at once without the lock
            other = Rewriter("rules")
            other.start_model = lambda: started.append(name)
            return other
        main = Rewriter("rules")
        main.profile, main.loader, main.routed = "main", loader, {}
        threads = [threading.Thread(target=main.load, args=("small", "test")) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(started, ["small"])

if __name__ == "__main__":
    unittest.main()
