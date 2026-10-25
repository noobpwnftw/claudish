"""Warm subscription backends (claudish/warm.py) against stand-ins for their CLIs (tests/fake_cli.py)."""
import sys
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"XDG_CONFIG_HOME": folder}):
            rewriter = Rewriter("claude-code", command=[sys.executable, FAKE, "claude"], timeout=5)
            try:
                rewriter.start_model()
                self.assertEqual(ready(rewriter.warm), "warm")
                self.assertTrue(Path(folder, "claudish").is_dir())
                self.assertEqual(rewriter.model_state, "warm")
                self.assertTrue(rewriter.rewrite("ok")["text"].startswith("seen 1"))
            finally:
                rewriter.stop_model()


class LifecycleTests(unittest.TestCase):
    def backends(self):
        for kind, name in ((warm.ClaudeCode, "claude"), (warm.Codex, "codex")):
            backend = kind([sys.executable, FAKE, name])
            self.addCleanup(backend.stop)
            yield backend

    def test_stop_before_the_warmup_thread_runs_does_not_launch(self):
        for backend in self.backends():
            with self.subTest(backend=backend.name), patch.object(backend, "launch") as launch:
                backend.stop()
                backend.warm_up()
                launch.assert_not_called()
                self.assertEqual(backend.state, "stopped")

    def test_stop_between_answer_and_preparing_next_request_does_not_restart(self):
        for backend in self.backends():
            reached, resume = threading.Event(), threading.Event()
            finish = backend.finish

            def delayed_finish():
                reached.set()
                if not resume.wait(1):
                    raise RuntimeError("test did not resume warmup")
                finish()

            with self.subTest(backend=backend.name), patch.object(backend, "finish", delayed_finish):
                worker = threading.Thread(target=backend.warm_up)
                worker.start()
                try:
                    self.assertTrue(reached.wait(1))
                    process = backend.process
                    backend.stop()
                finally:
                    resume.set()
                    worker.join(1)
                self.assertFalse(worker.is_alive())
                self.assertIsNotNone(process.poll())
                self.assertFalse(backend.alive())
                self.assertEqual(backend.state, "stopped")

    def test_stop_during_spawn_ends_the_new_child(self):
        for backend in self.backends():
            spawn = warm.spawn
            children = []

            def stop_while_spawning(*args, **kwargs):
                process = spawn(*args, **kwargs)
                children.append(process)
                # stop sets its event before waiting for the spawn's lifecycle lock.
                backend.stopped.set()
                return process

            with self.subTest(backend=backend.name), patch.object(warm, "spawn", stop_while_spawning):
                backend.warm_up()
                self.assertTrue(children)
                self.assertTrue(all(child.poll() is not None for child in children))
                self.assertEqual(backend.state, "stopped")

    def test_failed_readiness_ends_the_child(self):
        for backend in self.backends():
            with self.subTest(backend=backend.name), patch.object(backend, "exchange", side_effect=TimeoutError):
                backend.warm_up()
                self.assertFalse(backend.alive())
                self.assertTrue(backend.state.startswith("failed:"))

    def test_stop_interrupts_an_inflight_request(self):
        for backend in self.backends():
            entered, errors = threading.Event(), []
            exchange = backend.exchange

            def request():
                try:
                    backend.ask("slow one", 30)
                except RuntimeError as exc:
                    errors.append(str(exc))

            def started_exchange(*args):
                entered.set()
                return exchange(*args)

            with self.subTest(backend=backend.name), patch.object(backend, "exchange", started_exchange):
                worker = threading.Thread(target=request)
                worker.start()
                try:
                    self.assertTrue(entered.wait(1))
                    backend.stop()
                finally:
                    worker.join(1)
                self.assertFalse(worker.is_alive())
                self.assertEqual(len(errors), 1)
                self.assertFalse(backend.alive())
                self.assertEqual(backend.state, "stopped")

    def test_missing_binary_is_reported_as_a_model_error(self):
        for backend in self.backends():
            with self.subTest(backend=backend.name), patch.object(backend, "binary", return_value="/missing/cdai-cli"):
                with self.assertRaisesRegex(RuntimeError, backend.name):
                    backend.ask("rewrite", 1)
                self.assertEqual(backend.state, "restarting")


if __name__ == "__main__":
    unittest.main()
