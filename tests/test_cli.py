"""The claudish commands as people run them: a message and an exit code, never a traceback."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CommandTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(self.home), HOME=str(self.home), PYTHONPATH=str(ROOT))

    def claudish(self, *args, stdin=None):
        return subprocess.run([sys.executable, "-m", "claudish", *args], capture_output=True, text=True,
                              env=self.env, cwd=str(ROOT), timeout=60, input=stdin)

    def config(self, data):
        path = self.home / "claudish/config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data))

    def assertSaid(self, done, code, words):
        self.assertEqual(done.returncode, code, done.stderr[-400:])
        self.assertNotIn("Traceback", done.stderr)
        self.assertIn(words, done.stdout + done.stderr)

    def service(self):
        """A service with no model, as a first run has: (url, stop)."""
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        process = subprocess.Popen([sys.executable, "-m", "claudish", "serve", "--port", str(port)], env=self.env,
                                   cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(process.wait)
        self.addCleanup(process.terminate)
        token = self.home / "claudish" / ("service-token-%d" % port)
        deadline = time.monotonic() + 20
        while not token.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        return "http://127.0.0.1:%d" % port

    def test_a_service_that_refuses_is_said(self):
        url = self.service()
        self.assertSaid(self.claudish("rewrite", "hello", "--url", url), 1, "cd_AI's service answered 503")
        done = self.claudish("bench", "--runs", "1", "--url", url)
        self.assertEqual(done.returncode, 1)  # nothing answered: a failed measurement
        self.assertNotIn("Traceback", done.stderr)

    def test_a_config_that_does_not_read(self):
        self.config('{"profiles":')
        self.assertSaid(self.claudish("mcp", "list"), 2, "cannot read")
        self.assertSaid(self.claudish("mcp", "import", "--dry-run"), 2, "cannot read")
        self.config("[1]")
        self.assertSaid(self.claudish("mcp", "list"), 2, "not a cd_AI config")

    def test_context_test_says_what_each_mode_reads(self):
        (self.home / "a.md").write_text("A")
        (self.home / "b.md").write_text("B")
        self.config({"profile": "a", "profiles": {
            "a": {"backend": "rules", "context": [{"type": "file", "name": "a-notes", "path": str(self.home / "a.md")}],
                  "modes": {"rewrite": {"profile": "b"}}},
            "b": {"backend": "rules", "context": [{"type": "file", "name": "b-notes", "path": str(self.home / "b.md")}]}}})
        done = self.claudish("context", "test", "--app", "thunderbird")
        self.assertSaid(done, 0, "b-notes")  # rewrite reads its own profile's context
        self.assertIn("a-notes", done.stdout)
        self.config({"profile": "claude", "profiles": {"claude": {"backend": "claude"}}})
        self.assertSaid(self.claudish("context", "test", "--app", "x"), 0, "continue  not asked")

    def test_a_profile_flag_that_does_not_exist_is_said_at_once(self):
        self.config({"profile": "a", "profiles": {"a": {"backend": "rules"}}})
        done = subprocess.run([sys.executable, "-m", "claudish", "serve", "--port", "1", "--profile", "typo"],
                              capture_output=True, text=True, env=self.env, cwd=str(ROOT), timeout=30)
        self.assertEqual(done.returncode, 2)
        self.assertIn("typo", done.stderr)

    def test_no_key_on_stdin_saves_nothing(self):
        done = subprocess.run([sys.executable, "-c", "import getpass, sys; getpass.getpass = lambda prompt: "
                               "(_ for _ in ()).throw(EOFError()); sys.argv = ['claudish', 'key'];"
                               "from claudish.__main__ import main; main()"],
                              capture_output=True, text=True, env=self.env, cwd=str(ROOT), timeout=30)
        self.assertSaid(done, 1, "No key given")


if __name__ == "__main__":
    unittest.main()
