"""Esc in the instruction's tool loop, against a real stdio MCP server (tests/mcp_server.py): its
own file, as a server still in a call takes a moment to end when the tests do."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish.conversation import ModelDriver
from claudish.model import Rewriter
from test_conversation import SERVER, Scripted, answer, run, setUpModule, tearDownModule  # noqa: F401 (own HOME)


class ToolStopTests(unittest.TestCase):
    def setUp(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest('needs the MCP SDK: pip install "claudish-ime[mcp]"')
        from claudish.tools import Toolbox
        self.rewriter = Rewriter()
        self.rewriter.modes["instruct"]["candidates"] = 1
        self.rewriter.toolbox = Toolbox(["notes"], SERVER, timeout=30)

    def question(self, session):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            for event in session.events:
                if event["type"] == "question" and event["id"] in session.questions:
                    return event
            time.sleep(0.05)
        self.fail("no question")

    def test_esc_during_a_tool_call_stops_it_and_asks_the_model_no_more(self):
        from claudish.tools import Toolbox
        slow = {"slow": {"command": sys.executable, "args": [str(Path(__file__).with_name("mcp_slow_server.py"))]}}
        self.rewriter.toolbox = Toolbox(["slow"], slow, timeout=30)
        model = Scripted(answer(calls=[("slow__wait", {"seconds": 4})]), answer("Late."))
        with patch.object(self.rewriter, "chat", model):
            session, thread = run(ModelDriver(self.rewriter, self.rewriter.conversations.get("box")), "wait")
            deadline = time.monotonic() + 15
            while not any(e["type"] == "progress" for e in session.events) and time.monotonic() < deadline:
                time.sleep(0.05)
            time.sleep(0.3)  # in the call
            stopped = time.monotonic()
            session.cancel()
            thread.join(15)
        self.assertLess(time.monotonic() - stopped, 2.5)  # not the rest of its 4 s
        self.assertEqual(len(model.sent), 1)  # and no model request after Esc

    def test_a_write_that_ran_is_remembered_when_the_turn_is_stopped(self):
        conversation = self.rewriter.conversations.get("box")
        model = Scripted(answer(calls=[("notes__pull_request_diff", {"number": 3})]), answer("Done."))
        holder = {}

        def chat(payload, headers, image=None, timeout=None):
            reply = model(payload, headers, image, timeout)
            if len(model.sent) == 2:
                holder["session"].cancel()  # Esc while the model writes its answer
            return reply
        with patch.object(self.rewriter, "chat", chat):
            session, thread = run(ModelDriver(self.rewriter, conversation), "look at PR 3")
            holder["session"] = session
            session.answer(self.question(session)["id"], 1)  # Allow
            thread.join(15)
        said = [m["content"] for m in conversation.messages if m["role"] == "assistant"]
        self.assertTrue(any("notes.pull_request_diff(number=3)" in each for each in said), said)
