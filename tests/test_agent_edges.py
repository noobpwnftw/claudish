"""The Claude Code driver against an agent that misbehaves (tests/fake_agent_edges.py)."""
import os
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from claudish.agent import AgentProcess, ClaudeCodeDriver
from claudish.sessions import Sessions
from serving import wait_until

COMMAND = [sys.executable, str(Path(__file__).with_name("fake_agent_edges.py"))]


@contextmanager
def running():
    """An agent for the block; its process and MCP config gone after (inside the block's patches)."""
    agent = AgentProcess(COMMAND)
    try:
        yield agent
    finally:
        agent.close(True)


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
            with running() as agent:
                self.assertEqual(turn(agent, "hello")[-1][0], "error")  # its first start failed
                self.assertEqual(turn(agent, "hello"), [("result", "ok")])  # a new session, not --resume
                self.assertEqual(turn(agent, "hello"), [("result", "ok")])  # and then resumed

    def test_a_line_that_is_not_a_message_does_not_carry_a_turn_into_the_next(self):
        with patch.dict(os.environ, {"FAKE_MODE": ""}):
            with running() as agent:
                self.assertEqual(turn(agent, "nonobj first"), [("result", "ANSWER TO FIRST")])
                self.assertEqual(turn(agent, "second instruction"), [("result", "answer to: second instruction")])

    def test_a_question_the_agent_withdraws_is_not_waited_for(self):
        import claudish.conversation as conversation
        with patch.dict(os.environ, {"FAKE_MODE": ""}), patch.object(conversation, "QUESTION_SECONDS", 1):
            with running() as agent:
                self.assertEqual(turn(agent, "cancelask"), [("question", "Q?"), ("result", "finished work")])

    def test_a_failed_turn_is_taken_back_from_the_agents_session(self):
        with patch.dict(os.environ, {"FAKE_MODE": ""}):
            with running() as agent:
                self.assertEqual(turn(agent, "first one"), [("result", "answer to: first one")])
                kept = agent.kept_at
                self.assertEqual(turn(agent, "fail this")[-1][0], "error")
                self.assertEqual((agent.kept_at, agent.resume_at), (kept, kept))  # resumed before the failure

    def test_a_turn_taken_back_stays_back_when_the_next_start_dies(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ, {"FAKE_MODE": "atcrash", "FAKE_LOG": folder + "/log"}):
            with running() as agent:
                turn(agent, "first one")
                turn(agent, "second one")
                agent.rewind(agent.kept_at)  # Esc took the second back
                kept = agent.resume_at
                self.assertEqual(turn(agent, "third")[-1][0], "error")  # that start died
                self.assertEqual(agent.resume_at, kept)  # the next start still resumes at the first

    def test_esc_while_the_agent_starts_sends_no_prompt(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"FAKE_MODE": "", "FAKE_LOG": folder + "/log"}):
            agent = AgentProcess(COMMAND)
            driver = ClaudeCodeDriver(COMMAND, agent=agent, timeout=60)
            starting = agent.ensure

            def ensure():
                starting()
                driver.cancel()  # Esc, while the process started
            agent.ensure = ensure
            try:
                session = Sessions().start(driver, "never sent")
                wait_until(lambda: not session.running, 5, 0.05)
                time.sleep(0.3)
                self.assertNotIn("never sent", Path(folder, "log").read_text())
            finally:
                agent.close(True)

    def test_an_ended_conversations_agent_starts_no_process(self):
        agent = AgentProcess(COMMAND)
        agent.close(ended=True)
        with self.assertRaisesRegex(RuntimeError, "had ended"):
            agent.ensure()
        self.assertIsNone(agent.process)


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
