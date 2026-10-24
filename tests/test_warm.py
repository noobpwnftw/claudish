"""Warm subscription backends (claudish/warm.py) against stand-ins for their CLIs (tests/fake_cli.py)."""
import sys
import time
import unittest
from pathlib import Path

from claudish import warm

FAKE = str(Path(__file__).with_name("fake_cli.py"))


def ready(backend, seconds=3.0):
    deadline = time.monotonic() + seconds
    while backend.state == "starting" and time.monotonic() < deadline:
        time.sleep(0.02)
    return backend.state


class ClaudeCodeTests(unittest.TestCase):
    def setUp(self):
        self.backend = warm.ClaudeCode([sys.executable, FAKE, "claude"])
        self.addCleanup(self.backend.stop)

    def test_it_starts_warm_and_each_request_is_its_own_conversation(self):
        self.backend.start()
        self.assertEqual(ready(self.backend), "warm")
        self.assertTrue(self.backend.alive())  # the next request's process, already started
        self.assertEqual(self.backend.ask("rewrite: ok", 5), "seen 1: rewrite: ok")
        self.assertEqual(self.backend.ask("rewrite: hi", 5), "seen 1: rewrite: hi")  # not "seen 2"

    def test_a_dead_process_is_replaced_and_a_slow_one_times_out(self):
        self.backend.start()
        ready(self.backend)
        self.backend.process.kill()
        self.backend.process.wait()
        self.assertEqual(self.backend.ask("after crash", 5), "seen 1: after crash")
        with self.assertRaisesRegex(RuntimeError, "longer than"):
            self.backend.ask("slow one", 0.5)
        self.assertEqual(self.backend.state, "restarting")
        self.assertEqual(self.backend.ask("and then", 5), "seen 1: and then")
        with self.assertRaisesRegex(RuntimeError, "ended"):
            self.backend.ask("die", 5)

    def test_stop_ends_the_process(self):
        self.backend.start()
        ready(self.backend)
        process = self.backend.process
        self.backend.stop()
        self.assertIsNotNone(process.poll())
        with self.assertRaisesRegex(RuntimeError, "stopping"):
            self.backend.ask("too late", 1)


class CodexTests(unittest.TestCase):
    def setUp(self):
        self.backend = warm.Codex([sys.executable, FAKE, "codex"], model="fast")
        self.addCleanup(self.backend.stop)

    def test_one_process_a_new_thread_per_request(self):
        self.backend.start()
        self.assertEqual(ready(self.backend), "warm")
        process = self.backend.process
        first, second = self.backend.ask("rewrite: ok", 5), self.backend.ask("rewrite: hi", 5)
        self.assertEqual((first, second), ("t2 turn 1 model fast: rewrite: ok", "t3 turn 1 model fast: rewrite: hi"))  # t1: the warm-up
        self.assertIs(self.backend.process, process)  # the same warm process

    def test_a_model_the_account_lacks_falls_back_to_the_default(self):
        self.backend.model = "nope"
        self.assertEqual(self.backend.ask("ok", 5)[:22], "t1 turn 1 model None: ")
        self.assertIsNone(self.backend.model)

    def test_death_timeout_and_restart_after_many(self):
        self.backend.start()
        ready(self.backend)
        self.backend.process.kill()
        self.backend.process.wait()
        self.assertTrue(self.backend.ask("after a crash", 5).startswith("t1 turn 1"))  # a fresh process
        with self.assertRaisesRegex(RuntimeError, "longer than"):
            self.backend.ask("slow one", 0.5)
        self.backend.restart_after = 1
        process = self.backend.process if self.backend.alive() else None
        self.backend.ask("one", 5)
        self.assertIsNot(self.backend.process, process)


class RewriterTests(unittest.TestCase):
    def test_the_profile_backend_runs_warm_and_says_so(self):
        from claudish.model import Rewriter
        rewriter = Rewriter("claude-code", command=[sys.executable, FAKE, "claude"], timeout=5)
        self.addCleanup(rewriter.stop_model)
        rewriter.start_model()
        self.assertEqual(ready(rewriter.warm), "warm")
        self.assertEqual(rewriter.model_state, "warm")
        self.assertTrue(rewriter.hosted)
        self.assertTrue(rewriter.rewrite("ok")["text"].startswith("seen 1"))


if __name__ == "__main__":
    unittest.main()
