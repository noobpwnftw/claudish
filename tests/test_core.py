import json
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from claudish.client import Suggestions, suggest
from claudish.composition import Composition, MAX_COMPOSITION
from claudish.model import Rewriter
from claudish.server import make_server


class CompositionTests(unittest.TestCase):
    def test_typing_dash_accept_and_keep_original(self):
        state = Composition()
        for char in "hello-world":
            state.insert(char)
        self.assertEqual(state.text, "hello—world")
        state.offer(state.revision, "Hello—world, thoughtfully considered.")
        self.assertEqual(state.commit(), "hello—world")
        state.insert("a")
        state.offer(state.revision, "A nuanced perspective.")
        self.assertEqual(state.commit(True), "A nuanced perspective.")

    def test_edit_focus_and_commit_invalidate_old_results(self):
        state = Composition()
        state.insert("x")
        revision = state.revision
        state.backspace()
        state.insert("x")
        self.assertFalse(state.offer(revision, "stale despite identical text"))
        revision = state.revision
        state.commit()
        self.assertFalse(state.offer(revision, "stale after focus loss"))

    def test_bound_and_backspace(self):
        state = Composition()
        state.change("a" * MAX_COMPOSITION)
        self.assertFalse(state.insert("b"))
        state.backspace()
        self.assertTrue(state.insert("b"))
        self.assertEqual(len(state.text), MAX_COMPOSITION)


class WorkerTests(unittest.TestCase):
    def test_debounce_and_discard_inflight_result(self):
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        calls = []

        def transport(text, endpoint, mode="rewrite", app=None, look=False):
            calls.append(text)
            if text == "old":
                started.set()
                release.wait(2)
            else:
                finished.set()
            return {"text": text.upper()}

        with patch("claudish.client.suggest", transport):
            worker = Suggestions(debounce=0.01)
            try:
                worker.schedule(1, "old")
                self.assertTrue(started.wait(1))
                worker.schedule(2, "intermediate")
                worker.schedule(3, "latest")
                release.set()
                self.assertTrue(finished.wait(1))
                deadline = time.monotonic() + 1
                result = None
                while result is None and time.monotonic() < deadline:
                    result = worker.poll()
                    time.sleep(0.001)
                self.assertEqual(result, (3, {"text": "LATEST"}))
                self.assertEqual(calls, ["old", "latest"])
            finally:
                release.set()
                worker.close()
                worker.thread.join(1)


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(Rewriter("rules"), 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.start()
        cls.url = "http://127.0.0.1:%s" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_real_http_unicode_and_explicit_backend(self):
        result = suggest("Use this—it is very important.", self.url)
        self.assertEqual(result["text"], "Leverage this—it is particularly crucial.")
        self.assertEqual(result["backend"], "rules")

    def test_demo_assets_and_same_origin_requests(self):
        for path, content_type, fragment in [
            ("/", "text/html", b"THE CLAUDISH TYPING ROOM"),
            ("/demo.js", "text/javascript", b"requestSuggestion"),
            ("/demo.css", "text/css", b"@media"),
        ]:
            with urlopen(self.url + path) as response:
                self.assertIn(content_type, response.headers["Content-Type"])
                self.assertIn(fragment, response.read())
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        request = Request(self.url + "/suggest", data=b'{"text":"very important"}',
                          headers={"Content-Type": "application/json", "Origin": self.url,
                                   "Sec-Fetch-Site": "same-origin"})
        with urlopen(request) as response:
            self.assertEqual(json.load(response)["text"], "particularly crucial")

    def test_demo_rejects_foreign_hosts_origins_and_asset_paths(self):
        for path, headers, code in [
            ("/health", {"Host": "attacker.example"}, 403),
            ("/../model.py", {}, 404),
            ("/web/index.html", {}, 404),
        ]:
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(self.url + path, headers=headers))
            self.assertEqual(error.exception.code, code)
        for headers in [{"Origin": "null"}, {"Origin": "http://localhost:9999"},
                        {"Origin": self.url, "Sec-Fetch-Site": "cross-site"}]:
            request = Request(self.url + "/suggest", data=b'{"text":"hello"}',
                              headers={"Content-Type": "application/json", **headers})
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 403)

    def test_bad_payload_and_browser_origin(self):
        for body, headers, status in [
            ({"text": "x" * 513}, {}, 400),
            ([], {}, 400),
            ({"text": "hello"}, {"Origin": "http://example.com"}, 403),
        ]:
            req = Request(self.url + "/suggest", data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json", **headers})
            with self.assertRaises(HTTPError) as error:
                urlopen(req)
            self.assertEqual(error.exception.code, status)

    def test_model_contract_and_truncation(self):
        from io import BytesIO
        response = {"choices": [{"message": {"content": "A thoughtful rewrite."},
                                  "finish_reason": "stop"}], "usage": {"completion_tokens": 5}}
        model = Rewriter()
        with patch("claudish.model.build_opener") as opener:
            opener.return_value.open.return_value = BytesIO(json.dumps(response).encode())
            self.assertEqual(model.rewrite("hello")["text"], "A thoughtful rewrite.")
            req = opener.return_value.open.call_args.args[0]
            payload = json.loads(req.data)
            self.assertEqual(payload["messages"][-1]["content"], "hello")
            self.assertEqual(payload["temperature"], 0)
            response["choices"][0]["finish_reason"] = "length"
            opener.return_value.open.return_value = BytesIO(json.dumps(response).encode())
            with self.assertRaisesRegex(RuntimeError, "token budget"):
                model.rewrite("hello")


if __name__ == "__main__":
    unittest.main()
