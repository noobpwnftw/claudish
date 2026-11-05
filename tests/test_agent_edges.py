"""The Claude Code driver against an agent that misbehaves (tests/fake_agent_edges.py)."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish.agent import AgentProcess, ClaudeCodeDriver
from claudish.sessions import Sessions

COMMAND = [sys.executable, str(Path(__file__).with_name("fake_agent_edges.py"))]


def turn(agent, prompt, wait=8):
    session = Sessions().start(ClaudeCodeDriver(COMMAND, agent=agent, timeout=60), prompt)
    deadline = time.monotonic() + wait
    while not session.done and time.monotonic() < deadline:
        time.sleep(0.05)
    return [(event["type"], event.get("text")) for event in session.events]


class AgentEdgeTests(unittest.TestCase):
    def test_an_agent_that_died_before_its_first_turn_is_not_resumed(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ, {"FAKE_MODE": "startcrash", "FAKE_MARK": folder + "/m-"}):
            agent = AgentProcess(COMMAND)
            try:
                self.assertEqual(turn(agent, "hello")[-1][0], "error")  # its first start failed
                self.assertEqual(turn(agent, "hello"), [("result", "ok")])  # a new session, not --resume
                self.assertEqual(turn(agent, "hello"), [("result", "ok")])  # and then resumed
            finally:
                agent.close(True)

    def test_a_line_that_is_not_a_message_does_not_carry_a_turn_into_the_next(self):
        with patch.dict(os.environ, {"FAKE_MODE": ""}):
            agent = AgentProcess(COMMAND)
            try:
                self.assertEqual(turn(agent, "nonobj first"), [("result", "ANSWER TO FIRST")])
                self.assertEqual(turn(agent, "second instruction"), [("result", "answer to: second instruction")])
            finally:
                agent.close(True)

    def test_a_question_the_agent_withdraws_is_not_waited_for(self):
        import claudish.conversation as conversation
        with patch.dict(os.environ, {"FAKE_MODE": ""}), patch.object(conversation, "QUESTION_SECONDS", 1):
            agent = AgentProcess(COMMAND)
            try:
                self.assertEqual(turn(agent, "cancelask"), [("question", "Q?"), ("result", "finished work")])
            finally:
                agent.close(True)


class PolicyNameTests(unittest.TestCase):
    def test_a_server_name_claude_code_rewrites_keeps_its_policy(self):
        for server, wire in (("notes", "mcp__notes__delete_branch"), ("my.notes", "mcp__my_notes__delete_branch"),
                             ("notes_", "mcp__notes___delete_branch")):
            with self.subTest(server=server):
                driver = ClaudeCodeDriver(COMMAND, policy={server: ({"ci_status"}, {"delete_branch"})})
                sent = []
                driver.send = sent.append
                driver.question(None, {"request_id": "r1", "request": {"subtype": "can_use_tool", "tool_name": wire,
                                                                         "input": {}}})
                self.assertEqual(sent[0]["response"]["response"]["behavior"], "deny")
