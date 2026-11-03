"""The local model's server (claudish/warm.py ModelServer): run by the service from a llama profile's command."""
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish import warm

FAKE_LLAMA = r"""
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/health" else 404)
        self.end_headers()
    def log_message(self, *args):
        pass
HTTPServer(("127.0.0.1", int(sys.argv[1])), Health).serve_forever()
"""


class ModelServerTests(unittest.TestCase):
    def test_the_local_model_runs_with_the_service_and_stops_with_it(self):
        import socket
        from claudish.model import Rewriter
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        url = "http://127.0.0.1:%d" % port
        rewriter = Rewriter("llama", url, command=[sys.executable, "-c", FAKE_LLAMA, str(port)])
        self.assertIsInstance(rewriter.warm, warm.ModelServer)
        rewriter.start_model()
        deadline = time.monotonic() + 5
        while rewriter.model_state != "warm" and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(rewriter.model_state, "warm")
        process = rewriter.warm.process
        rewriter.stop_model()  # the settings switched away, or the service stops
        self.assertIsNotNone(process.wait(5))
        self.assertEqual(rewriter.model_state, "stopped")
        self.assertIsNone(Rewriter("llama", url).warm)  # a server of your own: not cd_AI's to run

    def test_a_model_that_ends_as_it_starts_has_failed_and_is_not_started_again(self):
        server = warm.ModelServer([sys.executable, "-c", "raise SystemExit(3)"], "http://127.0.0.1:9")
        with patch.object(warm, "spawn", wraps=warm.spawn) as started:
            server.start()
            deadline = time.monotonic() + 5
            while not server.state.startswith("failed") and time.monotonic() < deadline:
                time.sleep(0.05)
            time.sleep(1.2)  # a restart would have come by now
        self.assertEqual(server.state, "failed: the local model ended as it started (exit 3)")
        self.assertEqual(started.call_count, 1)

    def test_a_model_that_loaded_too_slowly_starts_again_at_the_next_request(self):
        server = warm.ModelServer([sys.executable, "-c", "pass"], "http://127.0.0.1:9")
        with patch.object(server, "start") as start:
            server.state = "failed: the local model ended as it started (exit 3)"
            server.retry()  # would only fail again
            start.assert_not_called()
            server.state = warm.TIMED_OUT
            server.retry()
            server.retry()  # a second request meanwhile: one start
            start.assert_called_once_with()

    def test_stopped_while_it_starts_it_is_not_left_running(self):
        started, spawn = [], warm.spawn

        def slow(*args, **kwargs):
            time.sleep(0.3)  # the settings switch away meanwhile
            started.append(spawn(*args, **kwargs))
            return started[-1]
        server = warm.ModelServer([sys.executable, "-c", "import time; time.sleep(30)"], "http://127.0.0.1:9")
        with patch.object(warm, "spawn", slow):
            server.start()
            time.sleep(0.1)
            server.stop()
            time.sleep(0.5)
        self.assertEqual(server.state, "stopped")
        self.assertIsNotNone(started[0].wait(5))  # ended, not left running

    def test_a_routed_models_process_goes_on_through_a_reload(self):
        from claudish.model import Rewriter
        command = [sys.executable, "-c", "import time; time.sleep(30)"]

        def build():
            main = Rewriter("rules")
            main.profile = "main"
            main.loader = lambda name: Rewriter("llama", "http://127.0.0.1:9", command=command)
            return main
        old = build()
        routed = old.load("local")
        process_warm = routed.warm
        try:
            fresh = build()
            fresh.adoptable = old.hand_over()  # what the service's swap does
            old.stop_model()
            self.assertIs(fresh.load("local").warm, process_warm)  # taken up, not started cold
            self.assertNotEqual(process_warm.state, "stopped")
        finally:
            fresh.stop_model()
        self.assertEqual(process_warm.state, "stopped")  # the service's stop ends it

    def test_a_port_another_server_has_fails_and_is_not_started_again(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class Health(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass
        other = ThreadingHTTPServer(("127.0.0.1", 0), Health)  # a llama-server left running
        threading.Thread(target=other.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        url = "http://127.0.0.1:%d" % other.server_port
        try:
            server = warm.ModelServer([sys.executable, "-c", "raise SystemExit(1)"], url)
            with patch.object(warm, "spawn", wraps=warm.spawn) as started:
                server.start()
                deadline = time.monotonic() + 5
                while not server.state.startswith("failed") and time.monotonic() < deadline:
                    time.sleep(0.01)
            self.assertTrue(server.state.startswith("failed: something already answers at %s" % url), server.state)
            self.assertEqual(started.call_count, 0)
        finally:
            other.shutdown()
            other.server_close()

    def test_the_routed_local_model_becoming_the_one_in_use_goes_on(self):
        from claudish.model import Rewriter
        from claudish.server import make_server
        command = [sys.executable, "-c", "import time; time.sleep(30)"]
        local = lambda: Rewriter("llama", "http://127.0.0.1:9", command=command)
        main = Rewriter("rules")
        main.profile, main.loader = "main", lambda name: local()
        routed = main.load("local").warm
        routed.start()
        fresh = local()
        fresh.profile = "local"
        import os
        import tempfile
        from urllib.request import urlopen
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "config.json")
            path.write_text("{}")
            server = make_server(main, 0, reload=lambda: fresh, config_path=path)
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
            try:
                os.utime(path, ns=(1, 1))  # an edit made "local" the profile in use
                urlopen("http://127.0.0.1:%d/health" % server.server_port, timeout=5).close()
                self.assertIs(fresh.warm, routed)  # taken up, not a second server on its port
            finally:
                fresh.stop_model()
                routed.thread.join(5)  # not left checking its address while the interpreter ends
                server.shutdown()
                server.server_close()

    def test_a_new_local_model_command_starts_once_the_old_server_has_gone(self):
        import os
        import socket
        import tempfile
        from urllib.request import urlopen
        from claudish.model import Rewriter
        from claudish.server import make_server
        slow = FAKE_LLAMA.replace("HTTPServer((", "import os, signal\nsignal.signal(signal.SIGTERM, lambda *a: "
                                  "threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0))).start())\nHTTPServer((")
        slow = "import threading, time\n" + slow  # it answers a while after it is asked to end
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        url = "http://127.0.0.1:%d" % port
        old = Rewriter("llama", url, command=[sys.executable, "-c", slow, str(port)])
        old.start_model()
        fresh = Rewriter("llama", url, command=[sys.executable, "-c", slow, str(port), "another model"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "config.json")
            path.write_text("{}")
            server = make_server(old, 0, reload=lambda: fresh, config_path=path)
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
            try:
                deadline = time.monotonic() + 5
                while old.model_state != "warm" and time.monotonic() < deadline:
                    time.sleep(0.02)
                os.utime(path, ns=(1, 1))  # the edit gives the model another command
                urlopen("http://127.0.0.1:%d/health" % server.server_port, timeout=10).close()
                deadline = time.monotonic() + 5
                while fresh.model_state != "warm" and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertEqual(fresh.model_state, "warm")  # not "something already answers"
            finally:
                fresh.stop_model()
                fresh.warm.thread.join(5)
                server.shutdown()
                server.server_close()

    def test_llama_command_names_the_model_and_port(self):
        argv = warm.llama_command("/x/llama-server", "/m/gemma.gguf", 18766)
        self.assertEqual(argv[:7], ["/x/llama-server", "-m", "/m/gemma.gguf", "--host", "127.0.0.1", "--port", "18766"])


if __name__ == "__main__":
    unittest.main()
