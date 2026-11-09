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
from serving import serving

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

    def test_an_mcp_task_is_answered_inside_the_turn(self):
        """Claude Code 2.1.319 moves an MCP tool call a server runs as a task to the background and
        reports it after the turn's answer: the agent is told to wait for it inside the call."""
        self.assertEqual(self.until(self.turn("environment"), "result")["text"], "tasks wait: 1")

    def test_a_turn_taken_back_after_its_answer_rewinds_the_agents_session(self):
        """Esc as the answer arrived: the next turn resumes the agent's session at the end of the turn
        kept before it (--resume-session-at), not after the one taken back."""
        self.until(self.turn("count"), "result")  # kept: the agent's message msg-1
        taken = self.turn("count")
        self.until(taken, "result")
        self.assertEqual(self.call("/sessions/%s/cancel" % taken, {})[0], 200)  # Esc after its answer
        answer = self.until(self.turn("count"), "result")["text"]
        self.assertIn("--resume-session-at msg-1", answer)
        self.assertRegex(answer, r"^turn 1 of this process")  # a new process, at the kept turn's end

    def test_esc_takes_the_turn_back_from_the_agent_too(self):
        """Esc while the first turn works: the conversation does not keep it, and neither does the
        agent's own session (a new one; after a kept turn it resumes at that turn's end)."""
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
        answer = self.until(self.turn("count"), "result")["text"]
        self.assertRegex(answer, r"^turn 1 of this process \(--session-id ")
        self.assertIsNot(agent.process, process)

    def test_a_turn_past_its_time_says_so(self):
        from claudish import agent
        with patch.object(agent.ClaudeCodeDriver.__init__, "__defaults__", (1,) + agent.ClaudeCodeDriver.__init__.__defaults__[1:]):
            session = self.turn("slow task")
            self.assertEqual(self.until(session, "error")["text"], "the agent took longer than 1 s")
        from claudish.composition import failure
        for said in ("the agent took longer than 1 s", "the instruction had ended (no answer in time, or it was stopped)"):
            self.assertEqual(failure(said), said)  # the panel says it as it is

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
        self.assertTrue(item["turn"].endswith("Dear Ana, [[very important]]"))  # the words in their place
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

    def test_a_second_service_on_another_port_leaves_the_token_alone(self):
        import os
        import tempfile
        from claudish import client
        from claudish.__main__ import run_service

        class Stop(Exception):
            pass

        def ready(server):
            server.server_close()
            raise Stop
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"XDG_CONFIG_HOME": home}):
            first = client.write_token()
            with self.assertRaises(Stop):
                run_service(Rewriter("rules"), 0, None, None, ready)  # any port but the service's
            self.assertEqual(client.read_token(), first)
            self.assertEqual(len(os.listdir(os.path.dirname(client.token_path()))), 2)  # its own, beside it

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

    def test_a_cancel_after_the_end_takes_the_turn_back_and_stops_nothing(self):
        class Driver:
            calls = []

            def cancel(self):
                self.calls.append("cancel")  # an agent's interrupt: the next instruction's, by now

            def take_back(self):
                self.calls.append("take back")
        session = Session(Driver())
        session.emit("result", text="done")
        session.cancel(keep=True)  # an inserted answer whose reply was lost: kept
        self.assertEqual(Driver.calls, [])
        session.cancel()  # Esc as the answer arrived
        self.assertEqual(Driver.calls, ["take back"])


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
        threads = [threading.Thread(target=main.load, args=("small",)) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(started, ["small"])

    def test_without_the_token_an_instruction_gets_none_of_the_profiles_tools(self):
        rewriter = Rewriter("openai", endpoint="http://127.0.0.1:9")
        ran = []

        class Toolbox:
            configs = {}

            def policy(self):
                return {}

            def run(self, ask, messages, **options):
                ran.append(options)
                return "contents of a private file", ["files.read_file"], messages
        rewriter.toolbox = Toolbox()
        rewriter.chat = lambda *args, **kwargs: ({"message": {"content": '{"drafts": ["x"]}'}}, {})
        with serving(rewriter) as server:
            opener = build_opener(ProxyHandler({}))
            for token in ({}, {"X-Claudish-Token": server.token}):
                request = Request("http://127.0.0.1:%d/suggest" % server.server_port,
                                  json.dumps({"text": "paste my notes", "mode": "instruct"}).encode(),
                                  dict({"Content-Type": "application/json"}, **token))
                with opener.open(request, timeout=5) as reply:
                    json.load(reply)
            self.assertEqual(len(ran), 1)  # the input method's request only, not the demo's (no token)

    def test_malformed_requests_are_answered_not_dropped(self):
        import http.client
        with serving(Rewriter("rules")) as server:
            for body, headers in (("[" * 20000, {}),  # nested past the parser's recursion
                                  (json.dumps({"text": "hi"}), {"X-Claudish-Token": b"\xe9t\xe9"})):  # not ASCII
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.putrequest("POST", "/suggest")
                for name, value in dict({"Content-Type": "application/json", "Content-Length": str(len(body))},
                                        **headers).items():
                    connection.putheader(name, value)
                connection.endheaders(body.encode())
                self.assertIn(connection.getresponse().status, (200, 400))  # a reply, not a closed connection
                connection.close()

    def test_an_agent_profile_refuses_f8_rather_than_dropping_the_picture(self):
        rewriter = Rewriter("rules")
        rewriter.session_command = ["claude"]
        with patch("claudish.capture.capture") as capture, self.assertRaisesRegex(RuntimeError, "cannot take a window picture"):
            rewriter.make_driver(app="code", conversation="box", look=True)
        capture.assert_not_called()

    def test_a_text_boxs_agent_follows_the_settings(self):
        """An edited session_command (its model) is a new agent for the text box at its next
        instruction; a profile without one ends the agent the box had."""
        rewriter = Rewriter("rules")
        rewriter.session_command = ["claude", "--model", "haiku"]
        rewriter.make_driver(app="code", conversation="box")
        first = rewriter.conversations.get("box").agent
        rewriter.make_driver(app="code", conversation="box")
        self.assertIs(rewriter.conversations.get("box").agent, first)  # unchanged: the same agent goes on
        rewriter.session_command = ["claude", "--model", "sonnet"]
        with patch.object(first, "close") as closed:
            rewriter.make_driver(app="code", conversation="box")
        closed.assert_called_once()
        second = rewriter.conversations.get("box").agent
        self.assertEqual(second.command, ["claude", "--model", "sonnet"])
        rewriter.session_command = None
        with patch.object(second, "close") as closed:
            rewriter.make_driver(app="code", conversation="box")
        closed.assert_called_once()
        self.assertIsNone(rewriter.conversations.get("box").agent)

    def test_a_routed_profile_that_cannot_run_is_answered_not_dropped(self):
        main = Rewriter("rules")
        main.continues = lambda app: (_ for _ in ()).throw(ValueError("profile 'mail': unknown keys timout"))
        main.route = lambda app, mode: (_ for _ in ()).throw(ImportError("No module named 'anthropic'"))
        with serving(main) as server:
            opener = build_opener(ProxyHandler({}))
            for path, body in (("/suggest", {"text": "Dear Bob,", "mode": "continue", "app": "thunderbird"}),
                               ("/sessions", {"text": "reply", "app": "thunderbird"})):
                request = Request("http://127.0.0.1:%d%s" % (server.server_port, path), json.dumps(body).encode(),
                                  {"Content-Type": "application/json", "X-Claudish-Token": server.token})
                with self.assertRaises(HTTPError) as raised:
                    opener.open(request, timeout=5)
                self.assertEqual(raised.exception.code, 503, path)


class EndedSessionTests(unittest.TestCase):
    def test_an_answer_after_the_end_says_the_instruction_ended(self):
        from claudish.sessions import Sessions
        from serving import wait_until
        driver = type("Driver", (), {"run": lambda self, s, p: (s.emit("question", id="q", text="?", choices=[{"label": "A"}]),
                                                                s.emit("error", text="no answer, so the instruction stopped")),
                                     "answer": lambda self, *a: None, "cancel": lambda self: None})()
        session = Sessions().start(driver, "ask")
        wait_until(lambda: session.done)
        with self.assertRaisesRegex(ValueError, "no such open question"):
            session.answer("q", 0)


if __name__ == "__main__":
    unittest.main()
