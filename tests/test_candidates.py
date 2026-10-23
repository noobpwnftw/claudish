import json
import unittest
from io import BytesIO
from unittest.mock import patch

from claudish.composition import Composition


def to_mode(state, mode):
    while state.mode != mode:
        state.next_mode()
from claudish.model import Rewriter


def reply(text):
    return BytesIO(json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}).encode())


class CompositionTests(unittest.TestCase):
    def instruct(self):
        state = Composition()
        to_mode(state, "instruct")
        state.insert("x")
        return state

    def test_digits_pick_only_from_an_instructions_list(self):
        state = Composition()
        state.insert("I have")
        state.offer(state.revision, "I possess", ["I hold"])
        self.assertFalse(state.choosing)  # while typing, "2" is text
        self.assertIsNone(state.pick(2))
        state = self.instruct()
        state.offer(state.revision, "One.", ["Two.", "One.", ""])
        self.assertEqual(state.candidates, ["One.", "Two."])  # deduplicated, empties dropped
        self.assertTrue(state.choosing)
        self.assertIsNone(state.pick(3))
        self.assertEqual(state.pick(2), "Two.")
        self.assertEqual((state.text, state.candidates), ("", []))

    def test_a_stale_list_is_dropped(self):
        state = self.instruct()
        revision = state.revision
        state.insert("y")
        self.assertFalse(state.offer(revision, "One.", ["Two."]))
        self.assertFalse(state.choosing)


class ModeFeelTests(unittest.TestCase):
    """Each mode looks different at the caret: rewrite converts in place, instruct lists drafts."""

    def test_rewrite_tab_converts_in_place_and_esc_brings_your_words_back(self):
        state = Composition()
        state.mode = "rewrite"
        state.change("very good")
        self.assertEqual(state.tab(), "request")  # Tab asks for it
        self.assertEqual(state.tab(), "wait")  # asked already
        state.offer(state.revision, "Exceptionally good.")
        self.assertFalse(state.choosing)  # no list for a rewrite
        self.assertEqual(state.shown, "Exceptionally good.")  # in place as it arrives: you asked
        self.assertEqual((state.escape(), state.shown), ("back", "very good"))
        self.assertEqual(state.escape(), "keep")  # a second Esc: your words, as typed
        self.assertEqual(state.tab(), "convert")  # the rewrite again, without asking again
        self.assertEqual(state.enter(), "accept")  # Enter keeps the converted text
        self.assertFalse(state.insert("x"))  # typing on keeps it too (the adapter commits first)
        self.assertEqual(state.commit(), "Exceptionally good.")

    def test_a_leading_space_is_the_apps_not_the_compositions(self):
        state = Composition()
        state.mode = "rewrite"
        self.assertTrue(state.passes(" "))  # after the previous word: straight into the app
        state.insert("h")
        self.assertFalse(state.passes(" "))  # inside a phrase it is part of it
        state.mode = "continue"
        state.change("")
        self.assertFalse(state.passes(" "))  # continue types everything into the app anyway

    def test_rewrite_esc_while_asking_stops_and_keeps_your_words(self):
        state = Composition()
        state.mode = "rewrite"
        state.change("very good")
        state.tab()
        revision = state.revision
        self.assertEqual((state.escape(), state.text, state.working), ("back", "very good", False))
        self.assertFalse(state.offer(revision, "Late."))  # the stopped request's answer is ignored

    def test_rewrite_backspace_after_converting_is_your_words_again(self):
        state = Composition()
        state.mode = "rewrite"
        state.change("hi")
        state.offer(state.revision, "Hello.")
        state.tab()
        state.backspace()
        self.assertEqual((state.shown, state.text, state.candidate), ("hi", "hi", "Hello."))

    def test_instruct_esc_closes_the_drafts_then_drops_the_instruction(self):
        state = Composition()
        state.mode = "instruct"
        state.change("say hi")
        state.submit()
        revision = state.revision
        self.assertEqual((state.escape(), state.text, state.working), ("back", "say hi", False))
        self.assertFalse(state.offer(revision, "Hi."))  # the answer to the stopped request is ignored
        state.submit()
        state.offer(state.revision, "Hi.", ["Hello there."])
        self.assertEqual((state.escape(), state.text, state.candidates), ("back", "say hi", []))
        self.assertEqual((state.escape(), state.text), ("drop", ""))  # nothing is inserted
        self.assertEqual(state.escape(), "pass")  # with nothing composed, Esc is the app's


class ContinueTests(unittest.TestCase):
    def test_continue_asks_only_at_a_word_boundary(self):
        state = Composition()
        self.assertEqual(state.mode, "continue")
        for typed, asks in (("Thanks for the rev", False), ("Thanks for the review ", True),
                            ("Hi Sam,", True), ("it seems", False), ("über", False), ("done.", True)):
            state.change(typed)
            self.assertEqual(state.automatic, asks, typed)
        state.change("Thanks for the review ")
        state.candidate = "Thanks for the review on the parser change."
        self.assertEqual(state.take_ghost(), "on the parser change.")
        self.assertFalse(state.automatic)  # taking it is not a pause: nothing more until the next key
        state.change(state.text + " ")
        self.assertTrue(state.automatic)
        state.next_mode(), state.next_mode()  # rewrite asks on Tab, not on pauses
        state.change("very")
        self.assertFalse(state.automatic)


class RewriterTests(unittest.TestCase):
    def test_rules_offer_three_readings_of_an_instruction_and_one_rewrite(self):
        rewriter = Rewriter("rules")
        self.assertEqual(rewriter.rewrite("say hi", mode="instruct")["candidates"],
                         ["As requested—say hi.", "Certainly—as requested—say hi.", "Of course—as requested—say hi."])
        self.assertEqual(len(rewriter.rewrite("very good")["candidates"]), 1)

    def test_first_reading_is_deterministic_and_the_rest_sampled(self):
        rewriter = Rewriter()
        with patch.object(rewriter, "opener") as opener:
            opener.open.side_effect = [reply("Hello."), reply("Hello."), reply("Hi there.")]
            result = rewriter.rewrite("say hi", mode="instruct")
            payloads = [json.loads(call.args[0].data) for call in opener.open.call_args_list]
        self.assertEqual([p["temperature"] for p in payloads], [0, 0.9, 0.9])
        self.assertEqual([p.get("seed") for p in payloads], [None, 1, 2])
        self.assertEqual(result["candidates"], ["Hello.", "Hi there."])
        self.assertEqual(result["text"], "Hello.")

    def test_a_failed_extra_sample_only_shortens_the_list(self):
        rewriter = Rewriter()
        with patch.object(rewriter, "opener") as opener:
            opener.open.side_effect = [reply("Hello."), OSError("busy"), reply("Hey.")]
            self.assertEqual(rewriter.rewrite("say hi", mode="instruct")["candidates"], ["Hello.", "Hey."])
            opener.open.side_effect = [OSError("down")]
            with self.assertRaises(OSError):  # the first reading failing is a real failure
                rewriter.rewrite("say hi", mode="instruct")

    def test_profiles_set_the_count_per_mode(self):
        from claudish import config
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "config.json")
            for count, ok in ((1, True), (5, True), (0, False), (6, False), (True, False)):
                path.write_text(json.dumps({"profiles": {"p": {"modes": {"instruct": {"candidates": count}}}}}))
                if ok:
                    _, settings, _, _ = config.resolve(path)
                    self.assertEqual(Rewriter.from_settings(settings).modes["instruct"]["candidates"], count)
                else:
                    with self.assertRaisesRegex(ValueError, "1 to 5"):
                        config.resolve(path)


if __name__ == "__main__":
    unittest.main()
