import json
import unittest
from io import BytesIO
from unittest.mock import patch

from claudish.composition import Composition
from claudish.model import Rewriter


def reply(text):
    return BytesIO(json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}).encode())


class CompositionTests(unittest.TestCase):
    def instruct(self):
        state = Composition()
        state.insert("x")
        state.next_mode(), state.next_mode()
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
