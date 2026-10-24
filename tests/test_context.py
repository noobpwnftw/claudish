import json
import sys
import tempfile
import threading
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from claudish import config
from claudish.context import Binding, Context
from claudish.model import Rewriter
from claudish.server import make_server


def joined(context):
    return "\n".join(text for _, text in context.sections())


class ContextTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "glossary.md").write_text("Fjordline: the ferry company.", encoding="utf-8")

    def test_file_and_command_providers_render_with_caret(self):
        context = Context([{"type": "file", "path": "glossary.md"},
                           {"type": "command", "name": "diff", "command": [sys.executable, "-c", "print('+ add retry')"]},
                           {"type": "command", "command": "%s -c \"print('string form')\"" % sys.executable}],
                          base=self.root)
        found = dict(context.sections())
        self.assertEqual(found["glossary.md"], "Fjordline: the ferry company.")
        self.assertEqual(found["diff"].strip(), "+ add retry")
        self.assertIn("string form", "".join(found.values()))
        self.assertEqual(Context().sections(), [])  # the text around the caret is the text box's, not a provider's

    def test_cache_ttl(self):
        context = Context([{"type": "file", "path": "glossary.md", "ttl": 60}], base=self.root)
        joined(context)
        (self.root / "glossary.md").write_text("changed", encoding="utf-8")
        self.assertIn("Fjordline", joined(context))  # still cached
        context.providers[0].expires = 0
        self.assertIn("changed", joined(context))

    def test_failing_or_slow_providers_do_not_block_rewrites(self):
        context = Context([{"type": "command", "command": [sys.executable, "-c", "import sys; sys.exit(3)"]},
                           {"type": "command", "timeout": 0.2,
                            "command": [sys.executable, "-c", "import time; time.sleep(5)"]},
                           {"type": "file", "path": "missing.md"}], base=self.root)
        self.assertEqual(joined(context), "")
        self.assertIn("exit status 3", context.providers[0].error)

    def test_budget_truncates(self):
        (self.root / "big.md").write_text("x" * 5000, encoding="utf-8")
        context = Context([{"type": "file", "path": "big.md"}, {"type": "file", "path": "glossary.md"}],
                          base=self.root, max_chars=1000)
        block = joined(context)
        self.assertIn("x" * 1000, block)
        self.assertNotIn("x" * 1001, block)
        self.assertNotIn("Fjordline", block)

    def test_config_validation_and_relative_paths(self):
        path = self.root / "config.json"
        for spec, message in [({"type": "web"}, "type must be"), ({"type": "file", "path": "a", "x": 1}, "unknown keys x"),
                              ({"type": "command"}, "needs a"), ("not an object", "list of objects")]:
            path.write_text(json.dumps({"profiles": {"p": {"context": [spec]}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, message):
                config.resolve(path)
        path.write_text(json.dumps({"profiles": {"p": {"context": [{"type": "file", "path": "glossary.md"}],
                                                       "max_context_chars": 500}}}), encoding="utf-8")
        _, _, _, context = config.resolve(path)
        self.assertEqual(context.max_chars, 500)
        self.assertIn("Fjordline", joined(context))

    def test_context_reaches_the_model_prompt(self):
        rewriter = Rewriter(context=Context([{"type": "file", "path": "glossary.md"}], base=self.root))
        reply = {"choices": [{"message": {"content": "Very well."}, "finish_reason": "stop"}]}
        with patch("claudish.model.build_opener") as opener:
            opener.return_value.open.return_value = BytesIO(json.dumps(reply).encode())
            rewriter.rewrite("ok", before="Dear Zoë,")
            messages = json.loads(opener.return_value.open.call_args.args[0].data)["messages"]
        system, turn = messages[0]["content"], messages[-1]["content"]
        self.assertTrue(system.startswith(rewriter.modes["rewrite"]["system"]))
        self.assertIn("Dear Zoë,▮", system)  # the text box is described in the system prompt
        # What was observed goes next to the user's words, fenced as material.
        self.assertIn("Fjordline: the ferry company.", turn)
        self.assertTrue(turn.startswith("Reference material") and turn.endswith("\n\nok"))

    def test_service_validates_caret_text(self):
        server = make_server(Rewriter("rules"), 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            url = "http://127.0.0.1:%s/suggest" % server.server_port
            for body, status in [({"text": "very good", "before": "x" * 4000}, 200),
                                 ({"text": "very good", "before": "x" * 4001}, 400),
                                 ({"text": "very good", "after": 5}, 400)]:
                request = Request(url, data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json", "X-Claudish-Token": server.token})
                if status == 200:
                    with urlopen(request) as reply:
                        self.assertEqual(json.load(reply)["text"], "particularly good")
                else:
                    with self.assertRaises(HTTPError) as error:
                        urlopen(request)
                    self.assertEqual(error.exception.code, status)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class BindingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "pr.md").write_text("PR #42 adds retries.", encoding="utf-8")

    def test_bindings_add_context_only_for_matching_apps(self):
        binding = Binding({"app": "Firefox*", "context": [{"type": "file", "name": "pr", "path": "pr.md"}]}, self.root)
        self.assertTrue(binding.matches("firefox") and binding.matches("firefox-esr"))
        self.assertFalse(binding.matches("gedit") or binding.matches(None))
        rewriter = Rewriter("rules", bindings=[binding])
        self.assertEqual(rewriter.rewrite("very good", app="firefox")["consulted"], ["pr"])
        self.assertEqual(rewriter.rewrite("very good", app="gedit")["consulted"], [])
        with patch("claudish.model.build_opener") as opener:
            reply = {"choices": [{"message": {"content": "Indeed."}, "finish_reason": "stop"}]}
            opener.return_value.open.return_value = BytesIO(json.dumps(reply).encode())
            Rewriter(bindings=[binding]).rewrite("ok", app="firefox")
            turn = json.loads(opener.return_value.open.call_args.args[0].data)["messages"][-1]["content"]
        self.assertIn("PR #42 adds retries.", turn)

    def test_binding_config_and_service(self):
        path = self.root / "config.json"
        for spec, message in [({"context": []}, "binding is"), ({"app": "x", "mode": "instruct"}, "binding is")]:
            path.write_text(json.dumps({"profiles": {"p": {"bindings": [spec]}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, message):
                config.resolve(path)
        path.write_text(json.dumps({"profiles": {"p": {"bindings": [
            {"app": "gtk3-*", "context": [{"type": "file", "path": "pr.md"}]}]}}}), encoding="utf-8")
        _, settings, _, _ = config.resolve(path)
        server = make_server(Rewriter("rules", bindings=settings["bindings"]), 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            url = "http://127.0.0.1:%s/suggest" % server.server_port
            request = Request(url, data=json.dumps({"text": "very good", "app": "gtk3-demo"}).encode(),
                              headers={"Content-Type": "application/json", "X-Claudish-Token": server.token})
            with urlopen(request) as reply:
                self.assertEqual(json.load(reply)["consulted"], ["pr.md"])
            request = Request(url, data=json.dumps({"text": "very good", "app": ["x"]}).encode(),
                              headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class MCPContextTests(unittest.TestCase):
    """Real stdio MCP round trips; skipped unless the optional MCP SDK is installed."""

    def setUp(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest('needs the MCP SDK: pip install "claudish-ime[mcp]"')
        self.server = [sys.executable, str(Path(__file__).with_name("mcp_server.py"))]

    def test_tool_resource_env_and_failures(self):
        with patch.dict("os.environ", {"SECRET_FOR_TEST": "t-42"}):
            context = Context([
                {"type": "mcp", "name": "pr", "command": self.server, "tool": "pull_request_diff",
                 "arguments": {"number": 7}, "env": {"TEST_TOKEN": "$SECRET_FOR_TEST"}, "timeout": 20},
                {"type": "mcp", "command": self.server, "resource": "notes://style", "timeout": 20},
                {"type": "mcp", "name": "broken", "command": self.server, "tool": "broken", "timeout": 20}])
        found = dict(context.sections())
        self.assertEqual(found["pr"], "PR #7: + retry the flaky upload (token t-42)")
        self.assertIn("Prefer em dashes.", "".join(found.values()))
        self.assertNotIn("broken", found)  # a failing provider contributes nothing
        self.assertIn("broken", context.providers[2].error)

    def test_url_transport_to_an_app_exposing_mcp(self):
        import socket
        import subprocess
        import time
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        server = subprocess.Popen(self.server + ["http", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(server.wait)
        self.addCleanup(server.terminate)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        url = "http://127.0.0.1:%d/mcp" % port
        with patch.dict("os.environ", {"APP_TOKEN": "t-7"}):
            context = Context([
                {"type": "mcp", "name": "app", "url": url, "headers": {"Authorization": "Bearer $APP_TOKEN"},
                 "tool": "pull_request_diff", "arguments": {"number": 9}, "timeout": 20},
                {"type": "mcp", "url": url, "resource": "notes://style", "timeout": 20}])
        self.assertEqual(context.providers[0].headers, {"Authorization": "Bearer t-7"})
        block = joined(context)
        self.assertIn("PR #9: + retry the flaky upload", block)
        self.assertIn("Prefer em dashes.", block)

    def test_spec_validation(self):
        for spec, message in [({"type": "mcp", "command": self.server}, "exactly one"),
                              ({"type": "mcp", "command": self.server, "tool": "a", "resource": "b"}, "exactly one"),
                              ({"type": "mcp", "command": self.server, "tool": "a", "env": {"A": 1}}, "env"),
                              ({"type": "mcp", "url": "http://x", "command": self.server, "tool": "a"}, "not both"),
                              ({"type": "mcp", "url": "file:///etc/passwd", "tool": "a"}, "http"),
                              ({"type": "mcp", "url": "http://x", "transport": "ws", "tool": "a"}, "transport"),
                              ({"type": "mcp", "url": "http://x", "tool": "a", "env": {"A": "b"}}, "started server")]:
            with self.assertRaisesRegex(ValueError, message):
                Context([spec])


if __name__ == "__main__":
    unittest.main()


class RoutingTests(unittest.TestCase):
    """Which AI answers where: a binding's "profile" routes an app's requests to that profile."""

    def config(self, folder, bindings):
        path = Path(folder) / "config.json"
        path.write_text(json.dumps({"profile": "main", "profiles": {
            "main": {"backend": "rules", "bindings": bindings},
            "plain": {"backend": "rules", "tone": "plain"}}}))
        return path

    def test_a_binding_routes_an_app_to_its_profile(self):
        import tempfile
        from claudish import config
        with tempfile.TemporaryDirectory() as folder:
            path = self.config(folder, [{"app": "slack*", "profile": "plain"}])
            name, settings, prompt, context = config.resolve(path)
            main = Rewriter.from_settings(settings, prompt, context, name)
            loaded = []

            def load(profile):
                loaded.append(profile)
                _, routed, routed_prompt, routed_context = config.resolve(path, profile)
                return Rewriter.from_settings(routed, routed_prompt, routed_context, profile)
            main.loader = load
            slack = main.route("slack")
            self.assertEqual(slack.profile, "plain")
            self.assertIn("in plain English", slack.modes["rewrite"]["system"])  # its tone, not main's
            self.assertIs(main.route("gedit"), main)
            self.assertIs(main.route("slack"), slack)  # built once
            self.assertEqual(loaded, ["plain"])
            self.assertIs(slack.sessions, main.sessions)  # one service: shared sessions and conversations
            server = make_server(main, 0)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            thread.start()
            try:
                url = "http://127.0.0.1:%d/suggest" % server.server_port
                for app, token, expected in (("slack", True, "plain"), ("gedit", True, "main"),
                                             ("slack", False, "main")):
                    headers = {"Content-Type": "application/json"}
                    body = {"text": "very good", "app": app}
                    if token:
                        headers["X-Claudish-Token"] = server.token
                    else:
                        body.pop("app")  # the demo's request: no app, the default profile
                    with patch.object(Rewriter, "rewrite", autospec=True,
                                      side_effect=lambda self, *a, **k: {"text": self.profile}) as rewrite:
                        with urlopen(Request(url, json.dumps(body).encode(), headers)) as reply:
                            self.assertEqual(json.load(reply)["text"], expected, (app, token))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_an_unknown_profile_in_a_binding_is_refused(self):
        import tempfile
        from claudish import config
        with tempfile.TemporaryDirectory() as folder:
            path = self.config(folder, [{"app": "slack*", "profile": "nope"}])
            with self.assertRaisesRegex(ValueError, "names profile 'nope'"):
                config.resolve(path)


class ModeRoutingTests(unittest.TestCase):
    def test_a_mode_can_name_the_profile_that_answers_it(self):
        from claudish import config
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({"profile": "main", "profiles": {
                "main": {"backend": "rules", "modes": {"continue": {"profile": "tiny"}},
                         "bindings": [{"app": "slack*", "profile": "chat"}]},
                "tiny": {"backend": "rules", "tone": "plain"},
                "chat": {"backend": "rules", "modes": {"instruct": {"profile": "strong"}}},
                "strong": {"backend": "rules"}}}))
            name, settings, prompt, context = config.resolve(path)
            main = Rewriter.from_settings(settings, prompt, context, name)
            main.loader = lambda profile: Rewriter.from_settings(*config.resolve(path, profile)[1:], profile)
            self.assertEqual(main.route("gedit", "continue").profile, "tiny")  # a small model at every pause
            self.assertIs(main.route("gedit", "instruct"), main)
            self.assertEqual(main.route("slack", "rewrite").profile, "chat")  # the app's profile
            self.assertEqual(main.route("slack", "instruct").profile, "strong")  # and its choice for the mode
            self.assertIs(main.route("slack", "instruct").sessions, main.sessions)
            path.write_text(json.dumps({"profiles": {"main": {"backend": "rules", "modes": {"continue": {"profile": "nope"}}}}}))
            with self.assertRaisesRegex(ValueError, "names profile 'nope'"):
                config.resolve(path)
