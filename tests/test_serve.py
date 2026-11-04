"""`claudish serve` at login: a model that cannot be set up leaves the input method running."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish import __main__ as cli
from claudish.model import Rewriter


class ServeTests(unittest.TestCase):
    def test_without_the_anthropic_sdk_the_service_runs_with_no_model_and_says_why(self):
        served = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "config.json")
            path.write_text('{"profile": "claude", "profiles": {"claude": {"backend": "claude"}}}')
            with patch.object(sys, "argv", ["claudish", "serve", "--config", str(path)]), \
                    patch.object(Rewriter, "from_settings", side_effect=ImportError("no anthropic")), \
                    patch.object(cli, "run_service", lambda rewriter, *rest: served.append(rewriter)), \
                    patch("sys.stderr"):
                cli.main()  # no SystemExit: a login service would start it again and again
        self.assertEqual(served[0].backend, "none")
        self.assertIn("Anthropic SDK", served[0].unavailable)
        self.assertIsNone(served[0].problem)  # the config reads: the settings window does not lock

    def test_a_templates_path_of_another_computers_home_is_a_config_problem(self):
        served = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "config.json")
            path.write_text('{"profile": "rules", "profiles": {"rules": {"backend": "rules",'
                            ' "templates": "~nobody-on-this-computer-zz/words.json"}}}')
            with patch.object(sys, "argv", ["claudish", "serve", "--config", str(path)]), \
                    patch.object(cli, "run_service", lambda rewriter, *rest: served.append(rewriter)), \
                    patch("sys.stderr"):
                cli.main()
        self.assertIn("home folder", served[0].problem)


class SavedKeyTests(unittest.TestCase):
    def test_a_key_saved_with_claudish_key_is_taken_up_without_a_restart(self):
        import os
        import threading
        from urllib.request import urlopen
        from claudish.server import make_server
        fresh, built = Rewriter("rules"), []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "config.json")
            path.write_text("{}")
            server = make_server(Rewriter("rules"), 0, reload=lambda: built.append(1) or fresh, config_path=path)
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
            try:
                urlopen("http://127.0.0.1:%d/health" % server.server_port, timeout=5).close()
                self.assertEqual(built, [])  # nothing changed
                Path(folder, "anthropic.key").write_text("sk-ant-test")
                os.utime(Path(folder, "anthropic.key"), ns=(1, 1))
                urlopen("http://127.0.0.1:%d/health" % server.server_port, timeout=5).close()
                self.assertEqual(built, [1])  # the next request builds the backend again, with the key
            finally:
                server.shutdown()
                server.server_close()


class SameProcessReloadTests(unittest.TestCase):
    def test_a_request_running_when_a_reload_keeps_the_model_process_still_has_it(self):
        """A tone changed while a rewrite runs: the same Claude Code process goes on, for the new
        settings and for the request already running on the old ones (it was taken from it)."""
        import os
        import threading
        from urllib.request import urlopen
        from claudish.server import make_server

        class Warm:
            command, configured, state, stopped = ["claude"], "haiku", "warm", False

            def stop(self):
                self.stopped = True

            def start(self):
                pass
        process = Warm()
        old, fresh = Rewriter("rules"), Rewriter("rules")
        old.warm, fresh.warm = process, Warm()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "config.json")
            path.write_text("{}")
            server = make_server(old, 0, reload=lambda: fresh, config_path=path)
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
            try:
                urlopen("http://127.0.0.1:%d/health" % server.server_port, timeout=5).close()
                path.write_text('{"tone": "x"}')
                os.utime(path, ns=(1, 1))
                urlopen("http://127.0.0.1:%d/health" % server.server_port, timeout=5).close()
                self.assertIs(server.rewriter, fresh)
                self.assertIs(fresh.warm, process)  # the same process goes on
                self.assertIs(old.warm, process)  # and the running request still has it
                self.assertFalse(process.stopped)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
