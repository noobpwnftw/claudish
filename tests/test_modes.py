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
        self.assertEqual(modes.finish("continue", "我今天", "去了商店。"), "我今天去了商店。")  # no space in CJK
        self.assertEqual(modes.finish("instruct", "say hi", "Hello—truly."), "Hello—truly.")
        # An echo of the text's last words (any case), quotes, and stray punctuation after a space.
        self.assertEqual(modes.finish("continue", "hello ", "Hello, how are you today?"), "hello how are you today?")
        self.assertEqual(modes.finish("continue", "Dear Sam,", '"I hope this finds you well."'),
                         "Dear Sam, I hope this finds you well.")

    def test_continue_never_offers_its_examples_or_what_is_already_there(self):
        examples = modes.defaults()["continue"]["examples"]
        first, second = examples[1]["content"], examples[3]["content"]  # the template's example answers
        done = "Sorry for the slow reply on %s " % first
        self.assertTrue(modes.parroted("continue", done, done + first, examples))
        self.assertTrue(modes.parroted("continue", done, done + second, examples))
        self.assertFalse(modes.parroted("continue", done, done + "Let's merge it today.", examples))
        self.assertFalse(modes.parroted("rewrite", "x", "x " + first, examples))
        # Nonsense in, the template's example out ("tttt" -> the meeting decline): not an answer.
        instruct = modes.defaults()["instruct"]["examples"]
        example = instruct[1]["content"]
        self.assertTrue(modes.parroted("instruct", "tttt", example, instruct))
        self.assertFalse(modes.parroted("instruct", instruct[0]["content"], example, instruct))  # asked for it
        self.assertFalse(modes.parroted("instruct", "tttt", "Could you clarify what you need?", instruct))

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
            self.assertIn("run when the user presses Enter", system)  # what the box's kind means
            self.assertNotIn("em dash", system)  # a command line has no tone
            # The screen goes with the instruction it explains; the prose examples stay out.
            self.assertTrue(turn.startswith("Reference material") and turn.endswith("\n\nfix"))
            self.assertIn("<context name=\"terminal screen, last lines\">", turn)
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
        # A draft for a terminal is one line: a newline at the prompt would run it without Enter.
        reply = "```bash\ngit status\n```\nThen run git push."
        with patch("claudish.screen.read", return_value=screen):
            result, _ = self.call(rewriter, "fix", "instruct", app="com.apple.Terminal", answer=reply)
        self.assertEqual(result["candidates"], ["git status"])
        from claudish.sessions import Sessions
        session = Sessions().start(type("Driver", (), {"run": lambda self, s, p: s.emit(
            "result", text="ls\nrm -rf /", candidates=["ls\nrm -rf /"])})(), "fix", one_line=True)
        events, _ = session.wait(0, timeout=2)
        self.assertEqual((events[-1]["text"], events[-1]["candidates"]), ("ls", ["ls"]))
        rules = Rewriter("rules")
        result = rules.rewrite("fix", mode="instruct", screen=screen)
        self.assertEqual(result["text"], "As requested—fix, having read the terminal.")
        self.assertIn("terminal screen (3 lines)", result["consulted"])

    def test_the_shipped_templates_are_a_valid_templates_file(self):
        from claudish.modes import load
        self.assertEqual(load(Path(modes.__file__).with_name("templates.json")), modes.TEMPLATES)
        self.assertEqual(set(modes.defaults()), {"rewrite", "continue", "instruct"})

    def test_a_profile_can_reword_the_box_too(self):
        rewriter = Rewriter(max_tokens=64, templates={"box": {"at_caret": "Write it for the caret."}})
        _, payload = self.call(rewriter, "decline politely", "instruct", before="Hi Sam,")
        self.assertTrue(payload["messages"][0]["content"].endswith("Write it for the caret."))
        self.assertEqual(rewriter.modes["instruct"]["box"]["kinds"], modes.TEMPLATES["box"]["kinds"])

    def test_the_tone_is_corporate_slop_unless_a_profile_sets_another(self):
        claudish = Rewriter(max_tokens=64)
        self.assertIn("corporate slop", claudish.modes["rewrite"]["system"])
        self.assertTrue(claudish.modes["instruct"]["examples"])
        for tone, word in (("salesman", "salesman"), ("critic", "critic"), ("bard", "bard")):
            named = Rewriter(max_tokens=64, tone=tone)  # each with its own wording and examples, in every mode
            for mode in ("rewrite", "continue", "instruct"):
                self.assertIn(word, named.modes[mode]["system"])
                self.assertTrue(named.modes[mode]["examples"])
            self.assertIn("a no stays a no", named.modes["rewrite"]["system"])  # the meaning is guarded in every tone
        plain = Rewriter(max_tokens=64, tone="plain and concise")
        for mode in ("rewrite", "continue", "instruct"):
            self.assertIn("plain and concise", plain.modes[mode]["system"])
            self.assertNotIn("slop", plain.modes[mode]["system"])
            self.assertEqual(plain.modes[mode]["examples"], [])  # Claudish's examples teach its tone
        proofread = Rewriter(max_tokens=64, tone="proofread")  # corrects, keeps your words
        self.assertIn("Keep their words", proofread.modes["rewrite"]["system"])
        self.assertIn("plain, natural", proofread.modes["instruct"]["system"])
        custom = Rewriter(max_tokens=64, templates={"modes": {"rewrite": {"system": "Translate to French."}}}, tone="plain")
        self.assertEqual(custom.modes["rewrite"]["system"], "Translate to French.")  # the profile's own words win
        self.assertIn("in the same language, plain.", custom.modes["continue"]["system"])  # the tone, where it names nothing
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({"profiles": {"work": {"backend": "rules", "tone": "formal British"}}}))
            _, settings, _, _ = config.resolve(path, "work")
            self.assertIn("formal British", Rewriter.from_settings(settings).modes["instruct"]["system"])
            path.write_text(json.dumps({"profiles": {"work": {"backend": "rules", "tone": "fix"}}}))
            with self.assertRaisesRegex(ValueError, '"fix" is now "proofread"'):
                config.resolve(path, "work")

    def test_a_terminal_screen_is_trimmed_to_its_last_lines(self):
        from claudish import screen
        padded = "C:\\> gti status   \r\n'gti' is not recognized   \r\n\r\nC:\\>      \r\n   \r\n"
        self.assertEqual(screen.tail(padded), "C:\\> gti status\n'gti' is not recognized\n\nC:\\>")
        self.assertEqual(screen.tail("\n".join(str(n) for n in range(100))).split("\n")[0], "60")
        self.assertTrue(screen.is_terminal("WindowsTerminal.exe") and screen.is_terminal("com.apple.Terminal"))
        self.assertFalse(screen.is_terminal("notepad.exe") or screen.is_terminal(None))
        # Secrets already on screen are replaced before the screen goes anywhere.
        shown = ("$ export API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456\nAKIAABCDEFGHIJKLMNOP\n"
                 "DB_PASSWORD=s3cret\n$ git commit -m 'fix token refresh'")
        text, count = screen.redact(shown)
        self.assertEqual(count, 3)
        self.assertNotIn("sk-abc", text)
        self.assertNotIn("s3cret", text)
        self.assertIn("DB_PASSWORD=[redacted]", text)
        self.assertIn("fix token refresh", text)  # words about tokens are not tokens
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

    def call(self, rewriter, text, mode, answer="the parser change.", **field):
        reply = {"choices": [{"message": {"content": answer}, "finish_reason": "stop"}]}
        with patch.object(rewriter, "opener") as opener:
            opener.open.side_effect = lambda *args, **kwargs: BytesIO(json.dumps(reply).encode())
            result = rewriter.rewrite(text, mode=mode, **field)
            return result, json.loads(opener.open.call_args.args[0].data)

    def test_each_mode_sends_its_template_and_budget(self):
        rewriter = Rewriter(max_tokens=64)
        result, payload = self.call(rewriter, "Thanks for the review on", "continue")
        self.assertEqual((result["text"], result["mode"]), ("Thanks for the review on the parser change.", "continue"))
        self.assertEqual(payload["messages"][0]["content"], modes.TEMPLATES["modes"]["continue"]["system"])
        self.assertEqual(payload["max_tokens"], 256)  # to the end of a sentence, in the tone
        _, payload = self.call(rewriter, "decline politely", "instruct")
        self.assertEqual((payload["messages"][0]["content"], payload["max_tokens"]), (modes.TEMPLATES["modes"]["instruct"]["system"], 2048))
        _, payload = self.call(rewriter, "so", "rewrite")
        self.assertEqual(payload["max_tokens"], 1024)  # the tone's paragraph, past the profile's 64
        with self.assertRaisesRegex(ValueError, "unknown mode"):
            rewriter.rewrite("so", mode="sing")

    def test_profile_overrides_and_new_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "words.json").write_text(json.dumps({"modes": {
                "instruct": {"max_tokens": 900}, "haiku": {"system": "Answer in a haiku.", "max_tokens": 60}}}))
            path = root / "config.json"
            path.write_text(json.dumps({"profiles": {"p": {"templates": "words.json"}}}))
            _, settings, templates, context = config.resolve(path)
            rewriter = Rewriter(templates=templates, context=context, modes=settings["modes"])
            self.assertEqual(rewriter.modes["instruct"]["max_tokens"], 900)  # only what the file names
            self.assertEqual(rewriter.modes["instruct"]["system"], modes.TEMPLATES["modes"]["instruct"]["system"])
            _, payload = self.call(rewriter, "autumn", "haiku")
            self.assertEqual((payload["messages"][0]["content"], payload["max_tokens"]), ("Answer in a haiku.", 60))
            for words, message in [({"modes": {"haiku": {}}}, "needs a"), ({"modes": {"instruct": {"temperature": 1}}}, "takes only"),
                                   ({"modes": {"instruct": {"max_tokens": "9"}}}, "integer")]:
                (root / "words.json").write_text(json.dumps(words))
                with self.assertRaisesRegex(ValueError, message):
                    config.resolve(path)
            for profile, message in [({"modes": {"instruct": {"max_tokens": 900}}}, "takes only"),
                                     ({"prompt": "words.json"}, "now")]:
                path.write_text(json.dumps({"profiles": {"p": profile}}))
                with self.assertRaisesRegex(ValueError, message):
                    config.resolve(path)

    def test_no_model_ships_compose_says_so_and_continue_only_where_it_costs_nothing(self):
        from claudish.composition import failure
        with self.assertRaisesRegex(RuntimeError, "no model is set up"):
            Rewriter("none").rewrite("ok")
        self.assertEqual(failure("no model is set up"), "no model is set up")
        # Continue asks at every pause: a local model (or the stand-in) answers it unasked; a
        # hosted one only where a profile routes continue to it.
        self.assertTrue(Rewriter("llama").autocompletes and Rewriter("rules").autocompletes)
        hosted = Rewriter("openai", "https://api.example.com")
        self.assertFalse(hosted.autocompletes or hosted.continues(None) or Rewriter("none").autocompletes)
        routed = Rewriter("openai", "https://api.example.com", modes={"continue": {"profile": "fast"}})
        routed.profile, routed.loader = "main", lambda name: Rewriter("llama")
        self.assertTrue(routed.continues(None))
        server = make_server(hosted, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            request = Request("http://127.0.0.1:%s/suggest" % server.server_port, headers={"Content-Type": "application/json"},
                              data=json.dumps({"text": "Thanks for the review ", "mode": "continue"}).encode())
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(json.load(caught.exception)["error"], "continue has no model of its own")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_service_modes_in_rules_mode(self):
        server = make_server(Rewriter("rules"), 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
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
