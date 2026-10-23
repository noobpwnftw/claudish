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
        # An echo of the text's last words (any case), quotes, and stray punctuation after a space.
        self.assertEqual(modes.finish("continue", "hello ", "Hello, how are you today?"), "hello how are you today?")
        self.assertEqual(modes.finish("continue", "Dear Sam,", '"I hope this finds you well."'),
                         "Dear Sam, I hope this finds you well.")

    def test_continue_never_offers_its_examples_or_what_is_already_there(self):
        examples = modes.defaults()["continue"]["examples"]
        done = "Sorry for the slow reply on the budget—this week got away from me. "
        self.assertTrue(modes.parroted("continue", done, done + "the budget—this week got away from me.", examples))
        self.assertTrue(modes.parroted("continue", done, done + "I hope this finds you well—a quick update on the release.", examples))
        self.assertFalse(modes.parroted("continue", done, done + "Let's merge it today.", examples))
        self.assertFalse(modes.parroted("rewrite", "x", "x the budget—this week got away from me.", examples))

    def test_every_mode_is_told_about_the_text_box(self):
        rewriter = Rewriter(max_tokens=64)
        _, payload = self.call(rewriter, "this is important", "rewrite", before="Dear Ana,\n\n", after="\n\nBest, Sam",
                               app="thunderbird", purpose="email")
        system = payload["messages"][0]["content"]
        self.assertIn("The text box is an email address field in thunderbird.", system)
        self.assertIn("Dear Ana,\n\n▮\n\nBest, Sam", system)  # where the rewrite goes
        _, payload = self.call(rewriter, "Thanks for the review ", "continue", after=" Cheers.", app="kate")
        system = payload["messages"][0]["content"]
        self.assertIn("The text box is a text field in kate.", system)
        self.assertIn("▮ Cheers.", system)  # continue: what follows the caret; the text itself is the frame
        _, payload = self.call(rewriter, "this is important", "rewrite")
        self.assertNotIn("text box", payload["messages"][0]["content"])  # nothing known: nothing added

    def test_a_terminal_is_read_for_an_instruction_never_for_continue(self):
        screen = "~ % gti status\nzsh: command not found: gti\n~ %"
        rewriter = Rewriter(max_tokens=64)
        with patch("claudish.screen.read", return_value=screen) as read:
            _, payload = self.call(rewriter, "fix", "instruct", app="com.apple.Terminal")
            system, turn = payload["messages"][0]["content"], payload["messages"][-1]["content"]
            self.assertIn("The text box is a terminal in com.apple.Terminal.", system)
            self.assertIn("lands at the prompt", system)
            self.assertIn("the command line", system)  # the terminal template, not the prose one
            # The screen goes with the instruction it explains; the prose examples stay out.
            self.assertTrue(turn.startswith("<terminal screen") and turn.endswith("\n\nfix"))
            self.assertIn("zsh: command not found: gti", turn)
            self.assertEqual(len(payload["messages"]), 2)
            self.call(rewriter, "ls -la ", "continue", app="com.apple.Terminal")
            self.assertEqual(read.call_count, 1)  # continue's pauses never read the screen
            _, payload = self.call(rewriter, "fix", "instruct", app="kate")  # not a terminal: never read
            self.assertEqual(read.call_count, 1)
            self.assertNotIn("terminal", payload["messages"][0]["content"])
            rewriter.read_terminal = False  # the profile's "read_terminal": false
            _, payload = self.call(rewriter, "fix", "instruct", app="gnome-terminal-server")
            self.assertEqual(read.call_count, 1)
            self.assertIn("The text box is a terminal", payload["messages"][0]["content"])
        rules = Rewriter("rules")
        result = rules.rewrite("fix", mode="instruct", screen=screen)
        self.assertEqual(result["text"], "As requested—fix, having read the terminal.")
        self.assertIn("terminal screen (3 lines)", result["consulted"])

    def test_a_terminal_screen_is_trimmed_to_its_last_lines(self):
        from claudish import screen
        padded = "C:\\> gti status   \r\n'gti' is not recognized   \r\n\r\nC:\\>      \r\n   \r\n"
        self.assertEqual(screen.tail(padded), "C:\\> gti status\n'gti' is not recognized\n\nC:\\>")
        self.assertEqual(screen.tail("\n".join(str(n) for n in range(100))).split("\n")[0], "60")
        self.assertTrue(screen.is_terminal("WindowsTerminal.exe") and screen.is_terminal("com.apple.Terminal"))
        self.assertFalse(screen.is_terminal("notepad.exe") or screen.is_terminal(None))
        # At a password prompt the screen is not sent (what you compose there would be the secret).
        with patch.object(screen, "read_atspi", return_value="$ sudo apt update\n[sudo] password for ana: "), \
                patch.object(screen.sys, "platform", "linux"):
            self.assertIsNone(screen.read("gnome-terminal-server"))
        with patch.object(screen, "read_atspi", return_value="$ ssh box\nEnter passphrase for key '/k': "), \
                patch.object(screen.sys, "platform", "linux"):
            self.assertIsNone(screen.read("gnome-terminal-server"))
        with patch.object(screen, "read_atspi", return_value="$ gti status\nbash: gti: command not found\n$ "), \
                patch.object(screen.sys, "platform", "linux"):
            self.assertEqual(screen.read("gnome-terminal-server").splitlines()[-1], "$")

    def test_continue_is_sent_as_quoted_text_not_as_a_message(self):
        rewriter = Rewriter(max_tokens=64)
        _, payload = self.call(rewriter, "hello ", "continue")
        self.assertEqual(payload["messages"][-1]["content"], 'Text so far: "hello "\nThe next few words:')
        _, payload = self.call(rewriter, "so", "rewrite")
        self.assertEqual(payload["messages"][-1]["content"], "so")  # other modes send the text itself

    def call(self, rewriter, text, mode, **field):
        reply = {"choices": [{"message": {"content": "the parser change."}, "finish_reason": "stop"}]}
        with patch.object(rewriter, "opener") as opener:
            opener.open.return_value = BytesIO(json.dumps(reply).encode())
            result = rewriter.rewrite(text, mode=mode, **field)
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
