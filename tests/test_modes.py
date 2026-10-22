import json
import tempfile
import threading
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from claudish import config, modes
from claudish.model import Rewriter
from claudish.server import make_server


class ModeTests(unittest.TestCase):
    def test_continue_joins_onto_the_typed_text(self):
        self.assertEqual(modes.finish("continue", "Thanks for", "the review."), "Thanks for the review.")
        self.assertEqual(modes.finish("continue", "Thanks for ", "the review."), "Thanks for the review.")
        self.assertEqual(modes.finish("continue", "It works", "—mostly."), "It works—mostly.")
        self.assertEqual(modes.finish("continue", "Thanks for", "Thanks for the review."), "Thanks for the review.")
        self.assertEqual(modes.finish("continue", "Thanks", "  "), "")
        self.assertEqual(modes.finish("instruct", "say hi", "Hello—truly."), "Hello—truly.")

    def call(self, rewriter, text, mode):
        reply = {"choices": [{"message": {"content": "the parser change."}, "finish_reason": "stop"}]}
        with patch.object(rewriter, "opener") as opener:
            opener.open.return_value = BytesIO(json.dumps(reply).encode())
            result = rewriter.rewrite(text, mode=mode)
            return result, json.loads(opener.open.call_args.args[0].data)

    def test_each_mode_sends_its_template_and_budget(self):
        rewriter = Rewriter(max_tokens=64)
        result, payload = self.call(rewriter, "Thanks for the review on", "continue")
        self.assertEqual((result["text"], result["mode"]), ("Thanks for the review on the parser change.", "continue"))
        self.assertEqual(payload["messages"][0]["content"], modes.CONTINUE_SYSTEM)
        self.assertEqual(payload["max_tokens"], 24)
        _, payload = self.call(rewriter, "decline politely", "instruct")
        self.assertEqual((payload["messages"][0]["content"], payload["max_tokens"]), (modes.INSTRUCT_SYSTEM, 400))
        _, payload = self.call(rewriter, "so", "rewrite")
        self.assertEqual(payload["max_tokens"], 64)
        with self.assertRaisesRegex(ValueError, "unknown mode"):
            rewriter.rewrite("so", mode="sing")

    def test_profile_overrides_and_new_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "haiku.json").write_text(json.dumps({"system": "Answer in a haiku.", "examples": []}))
            path = root / "config.json"
            path.write_text(json.dumps({"profiles": {"p": {"modes": {
                "instruct": {"max_tokens": 900}, "haiku": {"prompt": "haiku.json", "max_tokens": 60}}}}}))
            _, settings, prompt, context = config.resolve(path)
            rewriter = Rewriter(prompt=prompt, context=context, modes=settings["modes"])
            self.assertEqual(rewriter.modes["instruct"]["max_tokens"], 900)
            self.assertEqual(rewriter.modes["instruct"]["system"], modes.INSTRUCT_SYSTEM)
            _, payload = self.call(rewriter, "autumn", "haiku")
            self.assertEqual((payload["messages"][0]["content"], payload["max_tokens"]), ("Answer in a haiku.", 60))
            for spec, message in [({"haiku": {}}, "needs a"), ({"instruct": {"temperature": 1}}, "takes only"),
                                  ({"instruct": {"max_tokens": "9"}}, "integer")]:
                path.write_text(json.dumps({"profiles": {"p": {"modes": spec}}}))
                with self.assertRaisesRegex(ValueError, message):
                    config.resolve(path)

    def test_service_modes_in_rules_mode(self):
        server = make_server(Rewriter("rules"), 0)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            url = "http://127.0.0.1:%s" % server.server_port
            with urlopen(url + "/health") as reply:
                self.assertEqual(json.load(reply)["modes"], ["rewrite", "continue", "instruct"])
            for mode, expected in [("rewrite", "particularly good"), ("continue", "very good and then some—naturally."),
                                   ("instruct", "As requested—very good.")]:
                request = Request(url + "/suggest", data=json.dumps({"text": "very good", "mode": mode}).encode(),
                                  headers={"Content-Type": "application/json"})
                with urlopen(request) as reply:
                    self.assertEqual(json.load(reply)["text"], expected)
            request = Request(url + "/suggest", data=b'{"text": "very good", "mode": "sing"}',
                              headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
