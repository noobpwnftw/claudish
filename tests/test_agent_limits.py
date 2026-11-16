"""An agent turn's time limits (claudish/agent.py) against the fake agent (tests/fake_agent.py)."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish.agent import AgentProcess, ClaudeCodeDriver
from claudish.sessions import Sessions

AGENT = [sys.executable, str(Path(__file__).with_name("fake_agent.py"))]


class AgentLimitTests(unittest.TestCase):
    def test_an_agents_time_limit_leaves_out_your_waiting_and_a_question_has_its_own(self):
        driver = ClaudeCodeDriver(AGENT, timeout=0.5, agent=AgentProcess(AGENT))
        self.addCleanup(driver.agent.close, ended=True)
        with patch("claudish.conversation.QUESTION_SECONDS", 1.2):
            session = Sessions().start(driver, "hello")  # the fake agent asks "Allow Bash?" and waits
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not session.done:
                time.sleep(0.1)
        said = [e["text"] for e in session.events if e["type"] == "error"]
        self.assertEqual(said[:1], ["no answer, so the instruction stopped"])  # not "took longer than 0 s"


if __name__ == "__main__":
    unittest.main()
