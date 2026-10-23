import json
import sys
import threading
import unittest
import zlib
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from claudish import capture
from claudish.composition import Composition


def to_mode(state, mode):
    if state.mode != mode:
        state.toggle()
from claudish.model import Rewriter, user_content
from claudish.server import make_server

PNG = capture.encode_png(2, 1, [bytes([255, 0, 0, 0, 0, 255])])


class CompositionTests(unittest.TestCase):
    def test_f8_is_for_instructions_only_and_never_carries_over(self):
        state = Composition()
        state.insert("x")
        self.assertFalse(state.toggle_look())  # continue: nothing is sent as an instruction
        state.commit()
        to_mode(state, "compose")
        state.insert("x")
        revision = state.revision
        self.assertTrue(state.toggle_look() and state.look)
        self.assertGreater(state.revision, revision)  # a pending result was for the other choice
        state.insert("y")
        self.assertTrue(state.look)  # editing the instruction keeps the choice
        state.commit()
        self.assertFalse(state.look)  # the next instruction starts without a picture
        state.insert("z"), state.toggle_look(), state.toggle()
        self.assertFalse(state.look)


class CaptureTests(unittest.TestCase):
    def test_png_encoding_round_trips(self):
        self.assertEqual(capture.png_size(PNG), (2, 1))
        idat = PNG[PNG.index(b"IDAT") + 4:PNG.index(b"IEND") - 8]
        self.assertEqual(zlib.decompress(idat), b"\x00" + bytes([255, 0, 0, 0, 0, 255]))

    def test_bgra_is_shrunk_to_fit(self):
        width, height = capture.MAX_SIDE * 2 + 1, 3
        png = capture.bgra_to_png(bytes([1, 2, 3, 255]) * (width * height), width, height)
        self.assertLessEqual(max(capture.png_size(png)), capture.MAX_SIDE)

    def test_a_configured_command_writes_the_png(self):
        command = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(%r)" % PNG]
        self.assertEqual(capture.capture(command), (PNG, 2, 1))
        with self.assertRaisesRegex(capture.CaptureError, "not a PNG"):
            capture.capture([sys.executable, "-c", "print('hello')"])

    def test_no_capture_method_says_how_to_add_one(self):
        with patch("claudish.capture.platform.system", return_value="Darwin"):
            with self.assertRaisesRegex(capture.CaptureError, "look_command"):
                capture.capture()


@patch("claudish.capture.capture", return_value=(PNG, 2, 1))
class RewriterTests(unittest.TestCase):
    def test_rules_reports_the_picture_as_consulted(self, _):
        result = Rewriter("rules").rewrite("summarize this", mode="instruct", look=True)
        self.assertIn("window picture (2×1)", result["consulted"])
        self.assertIn("looked at the window", result["text"])
        with self.assertRaisesRegex(ValueError, "only taken for an instruction"):
            Rewriter("rules").rewrite("hello", look=True)

    def test_openai_compatible_backends_get_an_image_url(self, _):
        rewriter = Rewriter(max_tokens=64)
        reply = {"choices": [{"message": {"content": "A summary."}, "finish_reason": "stop"}]}
        with patch.object(rewriter, "opener") as opener:
            opener.open.return_value = BytesIO(json.dumps(reply).encode())
            rewriter.rewrite("summarize this", mode="instruct", look=True)
            content = json.loads(opener.open.call_args.args[0].data)["messages"][-1]["content"]
            self.assertTrue(content[0]["image_url"]["url"].startswith("data:image/png;base64,"))
            self.assertIn("summarize this", content[1]["text"])
            opener.open.side_effect = HTTPError("u", 500, "no vision", {}, BytesIO(b""))
            with self.assertRaisesRegex(RuntimeError, "vision model"):
                rewriter.rewrite("summarize this", mode="instruct", look=True)

    def test_claude_gets_an_image_block(self, _):
        content = user_content("summarize", PNG, "claude")
        self.assertEqual(content[0]["source"]["media_type"], "image/png")
        self.assertEqual(user_content("summarize", None, "claude"), "summarize")

    def test_the_command_backend_refuses(self, capture_mock):
        with self.assertRaisesRegex(RuntimeError, "cannot take a window picture"):
            Rewriter("command", command=["cat"]).rewrite("x", mode="instruct", look=True)
        capture_mock.assert_not_called()  # nothing is captured for a backend that cannot use it


class ServerTests(unittest.TestCase):
    def test_look_is_validated(self):
        server = make_server(Rewriter("rules"), 0)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        opener = build_opener(ProxyHandler({}))

        def post(body):
            request = Request("http://127.0.0.1:%d/suggest" % server.server_port, json.dumps(body).encode(),
                              {"Content-Type": "application/json"})
            try:
                with opener.open(request, timeout=5) as response:
                    return response.status, json.load(response)
            except HTTPError as exc:
                return exc.code, json.load(exc)
        try:
            self.assertEqual(post({"text": "hello", "look": True})[0], 400)  # not an instruction
            self.assertEqual(post({"text": "hello", "mode": "instruct", "look": "yes"})[0], 400)
            with patch("claudish.capture.capture", return_value=(PNG, 2, 1)):
                status, data = post({"text": "describe it", "mode": "instruct", "look": True})
            self.assertEqual(status, 200)
            self.assertIn("window picture (2×1)", data["consulted"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
