"""Configurable backends: Claude via a stand-in SDK, and OpenAI-compatible endpoints (no live services)."""
import importlib.util
import json
import os
import tempfile
import threading
from io import BytesIO
import types
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.request import urlopen

from claudish import modes
from claudish.model import Rewriter
from claudish.server import make_server


def response(text="A considered rewrite—truly.", stop_reason="end_turn"):
    return types.SimpleNamespace(
        stop_reason=stop_reason, usage=types.SimpleNamespace(input_tokens=90, output_tokens=12),
        content=[types.SimpleNamespace(type="thinking", thinking=""), types.SimpleNamespace(type="text", text=text)])


class FakeSDK:
    def __init__(self):
        self.calls = []
        self.reply = response()
        sdk = self

        class Anthropic:
            def __init__(self, **options):
                sdk.options = options
                self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=sdk.create))

            def with_options(self, **options):
                return self

        self.module = types.ModuleType("anthropic")
        self.module.Anthropic = Anthropic

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.reply


class ClaudeBackendTests(unittest.TestCase):
    def setUp(self):
        self.sdk = FakeSDK()
        patcher = patch.dict("sys.modules", {"anthropic": self.sdk.module})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_request_shape_and_result(self):
        rewriter = Rewriter("claude")
        result = rewriter.rewrite("Ship it.")
        self.assertEqual((result["text"], result["backend"]), ("A considered rewrite—truly.", "claude"))
        self.assertEqual(result["usage"], {"input_tokens": 90, "output_tokens": 12})
        call = self.sdk.calls[0]
        self.assertEqual(call["model"], "claude-opus-5-5")
        rewrite = modes.defaults()["rewrite"]
        self.assertEqual((call["system"], call["messages"]),
                         (rewrite["system"], rewrite["examples"] + [{"role": "user", "content": "Ship it."}]))
        self.assertEqual(call["output_config"], {"effort": "low"})
        self.assertEqual((call["fallbacks"], call["betas"]), ("default", ["server-side-fallback-2026-07-01"]))
        self.assertNotIn("temperature", call)
        self.assertEqual(self.sdk.options["max_retries"], 0)

    def test_haiku_omits_server_side_fallback(self):
        Rewriter("claude", claude_model="claude-haiku-5-5").rewrite("Ship it.")
        self.assertNotIn("fallbacks", self.sdk.calls[0])
        self.assertNotIn("betas", self.sdk.calls[0])

    def test_refusal_truncation_and_empty_output_are_never_offered(self):
        rewriter = Rewriter("claude")
        for reply, message in [(response("", "refusal"), "declined"),
                               (response("A half-fin", "max_tokens"), "token budget"),
                               (response("  "), "no text")]:
            self.sdk.reply = reply
            with self.assertRaisesRegex(RuntimeError, message):
                rewriter.rewrite("Ship it.")
        self.sdk.reply = response()
        self.assertEqual(rewriter.rewrite("Ship it.")["text"], "A considered rewrite—truly.")

    def test_missing_credentials_get_a_clear_message(self):
        def create(**kwargs):
            raise TypeError('"Could not resolve authentication method. Expected one of api_key"')
        self.sdk.create = create
        rewriter = Rewriter("claude")
        rewriter.claude.client.beta.messages.create = create
        with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY"):
            rewriter.rewrite("Ship it.")

    def test_one_request_at_a_time(self):
        rewriter = Rewriter("claude")
        with rewriter.lock:
            with self.assertRaisesRegex(RuntimeError, "busy"):
                rewriter.rewrite("Ship it.")
        self.assertEqual(self.sdk.calls, [])

    def test_health_reports_the_backend(self):
        for backend in ("claude", "rules"):
            server = make_server(Rewriter(backend), 0)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            thread.start()
            try:
                with urlopen("http://127.0.0.1:%s/health" % server.server_port) as reply:
                    self.assertEqual(json.load(reply), {"service": "cd_AI", "backend": backend, "routes": {},
                                                       "profile": None, "modes": ["rewrite", "continue", "instruct"],
                                                       "timeout": 3, "keys": {"summon": "Shift+Enter"}, "hints": True})
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


class EndpointBackendTests(unittest.TestCase):
    def call(self, rewriter):
        reply = {"choices": [{"message": {"content": "Indeed—so."}, "finish_reason": "stop"}]}
        with patch("claudish.model.build_opener") as opener:
            opener.return_value.open.side_effect = lambda *args, **kwargs: BytesIO(json.dumps(reply).encode())
            self.assertEqual(rewriter.rewrite("so")["text"], "Indeed—so.")
            request = opener.return_value.open.call_args_list[-1].args[0]  # the chat request (a nameless model asks /v1/models first)
            return opener.call_args.args, request, json.loads(request.data)

    def test_local_server_any_model_and_no_proxy(self):
        rewriter = Rewriter("openai", "http://localhost:11434/", model="qwen2.5:7b")
        self.assertFalse(rewriter.hosted)
        handlers, request, payload = self.call(rewriter)
        self.assertEqual(request.full_url, "http://localhost:11434/v1/chat/completions")
        self.assertEqual(payload["model"], "qwen2.5:7b")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(handlers[0].proxies, {})  # loopback bypasses HTTP_PROXY

    def test_remote_endpoint_is_hosted_and_sends_key(self):
        rewriter = Rewriter("openai", "https://models.example.com", model="any-model", api_key="k-123")
        self.assertTrue(rewriter.hosted)
        handlers, request, _ = self.call(rewriter)
        self.assertEqual(request.get_header("Authorization"), "Bearer k-123")
        self.assertEqual(handlers, ())  # default opener: system proxy settings apply


    def test_without_a_model_name_the_servers_only_model_is_used(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        listed, sent = [["gemma3:4b"]], []

        class Ollama(BaseHTTPRequestHandler):
            def do_GET(self):
                self.reply({"data": [{"id": name} for name in listed[0]]})

            def do_POST(self):
                sent.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.reply({"choices": [{"message": {"content": "Indeed—ok."}, "finish_reason": "stop"}]})

            def reply(self, data):
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = "http://127.0.0.1:%d" % server.server_port
        self.assertEqual(Rewriter("openai", url).rewrite("ok")["text"], "Indeed—ok.")
        self.assertEqual(sent[0]["model"], "gemma3:4b")  # Ollama refuses a request without one
        listed[0] = ["gemma3:4b", "qwen3:8b"]
        with self.assertRaisesRegex(RuntimeError, 'several models .*name one with "model"'):
            Rewriter("openai", url).rewrite("ok")

class PromptTemplateTests(unittest.TestCase):
    def write(self, data):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        with handle:
            json.dump(data, handle)
        self.addCleanup(lambda: __import__("os").unlink(handle.name))
        return handle.name

    def test_custom_template_reaches_both_backends(self):
        templates = modes.load(self.write({"modes": {"rewrite": {"system": "Be grand.",
                                                                 "examples": [["hi", "Greetings—hello."]]}}}))
        turns = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Greetings—hello."}]
        sdk = FakeSDK()
        with patch.dict("sys.modules", {"anthropic": sdk.module}):
            Rewriter("claude", templates=templates).rewrite("so")
        self.assertEqual(sdk.calls[0]["system"], "Be grand.")
        self.assertEqual(sdk.calls[0]["messages"][:2], turns)
        _, _, payload = EndpointBackendTests.call(self, Rewriter("openai", templates=templates))
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "Be grand."})

    def test_malformed_templates_are_rejected(self):
        for data in [{"rewrite": {"system": "x"}}, {"modes": {"rewrite": {"system": " "}}},
                     {"modes": {"rewrite": {"examples": [["only one"]]}}}, {"modes": {"haiku": {"max_tokens": 9}}},
                     {"modes": {"rewrite": {"temperature": 1}}}, {"modes": {"instruct": {"candidates": 6}}}]:
            with self.assertRaises(ValueError, msg=data):
                modes.load(self.write(data))


class CommandBackendTests(unittest.TestCase):
    """An agent CLI as the backend; a small Python script stands in for `claude -p`."""

    def agent(self, script, **options):
        import sys
        return Rewriter("command", command=[sys.executable, "-c", script], **options)

    def test_prompt_on_stdin_and_output_as_candidate(self):
        echo = "import sys; prompt = sys.stdin.read(); print('Drafted—' + prompt.split('Text:\\n')[-1].strip())"
        rewriter = self.agent(echo)
        self.assertTrue(rewriter.hosted)
        result = rewriter.rewrite("say hi; rm -rf ~ $(whoami)", mode="instruct")
        self.assertEqual(result["text"], "Drafted—say hi; rm -rf ~ $(whoami)")  # data, never a shell or argv
        dump = self.agent("import sys; print(sys.stdin.read())").rewrite("thanks", mode="instruct")["text"]
        self.assertTrue(dump.startswith("The user typed an instruction"))  # the mode's template comes first
        self.assertFalse(self.agent("print('x')", hosted=False).hosted)

    def test_failures_and_timeouts_keep_your_wording(self):
        with self.assertRaisesRegex(RuntimeError, "exit 3"):
            self.agent("import sys; sys.stderr.write('no auth'); sys.exit(3)").rewrite("hi")
        with self.assertRaisesRegex(RuntimeError, "longer than"):
            self.agent("import time; time.sleep(5)", timeout=0.3).rewrite("hi")
        with self.assertRaisesRegex(ValueError, "needs a"):
            Rewriter("command")


    def test_a_moved_claude_is_found_again(self):
        """Claude Code's updates move the binary a profile saved: the command finds it again."""
        import stat
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            claude = Path(folder, "claude")
            claude.write_text("#!/bin/sh\ncat\n")
            claude.chmod(claude.stat().st_mode | stat.S_IEXEC)
            rewriter = Rewriter("command", command=[str(Path(folder, "gone", "claude")), "-p"])
            with patch("claudish.settings.claude_code", return_value=str(claude)):
                self.assertIn("fine", rewriter.run_command("it is fine"))
            codex = Rewriter("command", command=[str(Path(folder, "old", "codex")), "exec", "-"])
            with patch("claudish.settings.codex", return_value=str(claude)):  # the same stand-in
                self.assertIn("fine", codex.run_command("it is fine"))

    def test_serve_cli_keeps_the_profile_command(self):
        import os
        import sys
        import tempfile
        from claudish import __main__ as cli
        with tempfile.TemporaryDirectory() as directory:
            os.makedirs(os.path.join(directory, "claudish"))
            with open(os.path.join(directory, "claudish", "config.json"), "w") as out:
                json.dump({"profiles": {"agent": {"backend": "command", "command": [sys.executable, "-c", "print(1)"]}}}, out)
            built = {}

            def make_server(rewriter, port, token=None, **settings_window):
                built["rewriter"] = rewriter
                raise SystemExit(0)

            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory}), \
                    patch.object(cli, "make_server", make_server), \
                    patch.object(sys, "argv", ["claudish", "serve"]):
                with self.assertRaises(SystemExit):
                    cli.main()
            self.assertEqual(built["rewriter"].command, [sys.executable, "-c", "print(1)"])



class ClaudeLoopTests(unittest.TestCase):
    """Claude with tools and a conversation: the same loop as any model (the tool calls translated)."""

    def setUp(self):
        self.sdk = FakeSDK()
        patcher = patch.dict("sys.modules", {"anthropic": self.sdk.module})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_claude_asks_and_drafts_through_the_loop(self):
        import time
        from claudish.conversation import ModelDriver
        from claudish.sessions import Session
        replies = [types.SimpleNamespace(stop_reason="tool_use", usage=types.SimpleNamespace(input_tokens=5, output_tokens=5),
                                         content=[types.SimpleNamespace(type="tool_use", id="tu1", name="user__ask",
                                                                        input={"question": "Did you mean git status?"})]),
                   response("git status")]
        self.sdk.create = lambda **kwargs: (self.sdk.calls.append(kwargs), replies.pop(0))[1]
        rewriter = Rewriter("claude")
        driver = ModelDriver(rewriter, rewriter.conversations.get("t"), purpose="terminal",
                             screen="$ gti status\nbash: gti: command not found\n$")
        session = Session(driver)
        thread = threading.Thread(target=lambda: driver.run(session, "fix"))
        thread.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not any(e["type"] == "question" for e in session.events):
            time.sleep(0.01)
        question = next(e for e in session.events if e["type"] == "question")
        session.answer(question["id"], 0)
        thread.join(5)
        self.assertEqual(session.events[-1]["text"], "git status")
        first, second = self.sdk.calls
        self.assertIn("user__ask", [tool["name"] for tool in first["tools"]])
        self.assertIn("run when the user presses Enter", first["system"])
        self.assertEqual(second["messages"][-2]["content"][0]["type"], "tool_use")
        result = second["messages"][-1]["content"][0]
        self.assertEqual((result["type"], result["tool_use_id"], result["content"]),
                         ("tool_result", "tu1", "The user chose: Yes"))


@unittest.skipUnless(importlib.util.find_spec("anthropic"), "the Anthropic SDK is not installed here")
class RealSdkTests(unittest.TestCase):
    """The real Anthropic SDK against a stand-in for Anthropic's API: what cd_AI sends (the endpoint,
    the model, the key) and what it makes of the answer. Anthropic itself needs a real key."""

    def test_a_rewrite_goes_through_the_sdk_as_sent_and_answered(self):
        import json as wire
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        seen = []

        class Anthropic(BaseHTTPRequestHandler):
            def do_POST(self):
                body = wire.loads(self.rfile.read(int(self.headers["Content-Length"])))
                # The SDK sends the key as x-api-key, or (2.x) as a bearer token: either way, the key.
                key = self.headers.get("x-api-key") or (self.headers.get("Authorization") or "").removeprefix("Bearer ")
                seen.append((self.path, key, body))
                answer = wire.dumps({"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
                                     "content": [{"type": "text", "text": "Absolutely—let's align on that."}],
                                     "stop_reason": "end_turn", "stop_sequence": None,
                                     "usage": {"input_tokens": 12, "output_tokens": 8}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)

            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Anthropic)
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        environment = {"ANTHROPIC_BASE_URL": "http://127.0.0.1:%d" % server.server_port, "ANTHROPIC_API_KEY": "sk-ant-test"}
        with patch.dict(os.environ, environment):
            result = Rewriter("claude", claude_model="claude-opus-5-5").rewrite("ok")
        self.assertEqual(result["text"], "Absolutely—let's align on that.")
        path, key, body = seen[0]
        self.assertEqual((path.split("?")[0], key, body["model"]), ("/v1/messages", "sk-ant-test", "claude-opus-5-5"))
        self.assertEqual(body["messages"][-1]["role"], "user")


if __name__ == "__main__":
    unittest.main()
