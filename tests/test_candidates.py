import json
import unittest
from io import BytesIO
from unittest.mock import patch

from claudish.composition import Composition


def to_mode(state, mode):
    if state.mode != mode:
        state.toggle()
from claudish.model import Rewriter


def reply(text):
    return BytesIO(json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}).encode())


class CompositionTests(unittest.TestCase):
    def instruct(self):
        state = Composition()
        to_mode(state, "compose")
        state.insert("x")
        state.submit()  # Enter: an instruction
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

    def test_tab_rewrites_in_place_and_esc_steps_back(self):
        state = Composition()
        state.mode = "compose"
        state.change("very good")
        self.assertEqual(state.tab(), "request")  # Tab asks for the rewrite
        self.assertEqual(state.tab(), "wait")  # asked already
        state.offer(state.revision, "Exceptionally good.")
        self.assertFalse(state.choosing)  # no list for a rewrite
        self.assertEqual(state.shown, "Exceptionally good.")  # in place as it arrives: you asked
        self.assertEqual((state.escape(), state.shown), ("back", "very good"))  # your words again
        self.assertEqual(state.tab(), "convert")  # the rewrite again, without asking again
        self.assertEqual(state.enter(), "accept")  # Enter keeps the rewrite shown
        self.assertFalse(state.insert("x"))  # typing on keeps it too (the adapter commits first)
        self.assertEqual(state.commit(), "Exceptionally good.")

    def test_esc_steps_back_until_what_you_composed_is_dropped(self):
        state = Composition()
        state.mode = "compose"
        state.change("very good")
        state.tab()
        state.offer(state.revision, "Exceptionally good.")
        self.assertEqual([state.escape() for _ in range(3)], ["back", "drop", "pass"])

    def test_shift_keeps_what_you_see_and_goes_to_continue(self):
        state = Composition()
        self.assertEqual((state.toggle(), state.mode, state.text), ("", "compose", ""))
        state.change("very good")
        self.assertEqual((state.toggle(), state.mode, state.text), ("very good", "continue", "very good"))
        state.toggle()
        state.change("hi")
        state.tab()
        state.offer(state.revision, "Hello.")
        self.assertEqual(state.toggle(), "Hello.")  # the rewrite shown is what you see

    def test_a_selection_taken_from_the_app_is_never_dropped(self):
        state = Composition()
        state.mode = "compose"
        state.adopt("their words")
        state.tab()
        state.offer(state.revision, "Their considered words.")
        self.assertEqual(state.escape(), "back")  # your words again
        self.assertEqual(state.escape(), "keep")  # and back into the app, as they were
        state.adopt("their words")
        self.assertEqual(state.escape(), "keep")  # even before any rewrite

    def test_shift_enter_keeps_it_as_it_is_and_stays_in_compose(self):
        state = Composition()
        state.mode = "compose"
        self.assertEqual(state.keep(), "")  # nothing composed: Shift+Enter is the app's
        state.change("as typed")
        self.assertEqual((state.keep(), state.mode, state.text), ("as typed", "compose", ""))

    def test_enter_sends_an_instruction_and_tab_a_rewrite(self):
        state = Composition()
        state.mode = "compose"
        state.change("decline politely")
        self.assertEqual(state.enter(), "submit")
        state.submit()
        self.assertEqual(state.request_mode, "instruct")
        state.offer(state.revision, "No, thank you.", ["Sadly, no."])
        self.assertTrue(state.choosing)  # an instruction's drafts are a list
        self.assertEqual(state.tab(), "accept")  # Tab takes the first draft, as Enter does
        state.change("decline politely")
        state.tab()
        self.assertEqual(state.request_mode, "rewrite")

    def test_a_space_keeps_the_drafts_and_a_quick_enter_waits(self):
        """Poll (a pinyin user): a reflexive Space must not throw away drafts you waited for, and a
        double-tapped Enter must not insert one nobody read."""
        state = Composition()
        state.mode = "compose"
        state.change("decline politely")
        state.submit()
        state.offer(state.revision, "No, thank you.", ["Sadly, no."])
        self.assertEqual(state.enter(), "wait")  # right after the drafts appear
        state.insert(" ")
        self.assertTrue(state.choosing)  # the space is held; the drafts stay
        self.assertEqual(state.shown, "decline politely ")
        state.backspace()
        self.assertTrue(state.choosing and state.text == "decline politely")
        state.insert(" ")
        self.assertEqual(state.pick(2), "Sadly, no.")
        state.change("decline politely")
        state.submit()
        state.offer(state.revision, "No, thank you.", ["Sadly, no."])
        state.insert(" ")
        state.insert("t")  # a letter refines the instruction: the drafts close
        self.assertFalse(state.choosing)
        self.assertEqual(state.text, "decline politely t")
        state.submit()
        state.offer(state.revision, "No, thank you.")
        state.offered_at -= 1  # a moment later, Enter takes the first draft
        self.assertEqual(state.enter(), "accept")

    def test_enter_takes_the_first_choice_of_a_question_but_never_approves(self):
        state = Composition()
        state.mode = "compose"
        state.change("fix")
        state.submit()
        state.ask(state.revision, {"id": "q", "text": "The model asks: Did you mean git status?",
                                   "choices": [{"label": "Yes"}, {"label": "No"}]}, "s")
        self.assertEqual((state.enter(), state.tab()), ("choose", "choose"))  # as with drafts
        state.answer_choice(1)
        state.ask(state.revision, {"id": "p", "text": "Allow notes.delete?", "permission": True,
                                   "choices": [{"label": "Allow"}, {"label": "Deny"}]}, "s")
        self.assertEqual(state.enter(), "wait")  # an approval needs a number
        self.assertEqual(state.tab(), "wait")

    def test_continue_waits_for_the_end_of_a_line(self):
        state = Composition()
        state.change("Thanks for the review ")
        self.assertTrue(state.automatic)
        state.inside = True  # text follows the caret on its line
        self.assertFalse(state.automatic)
        state.inside, state.quiet = False, True  # a number field
        self.assertFalse(state.automatic)

    def test_the_panel_is_the_labs_and_the_keys_wait_for_a_pause(self):
        """Composition.panel() is what every adapter draws (docs/design/visual.md): one header,
        rows with the highlighted one, one footer of keys with their verbs."""
        state = Composition()
        self.assertIsNone(state.panel())  # continue: no panel; the suggestion speaks for itself
        state.mode = "compose"
        state.change("say hi")
        typed = state.typed_at
        self.assertIsNone(state.panel(typed + 0.2))  # typing: only the composition
        self.assertAlmostEqual(state.hint_due(typed + 0.2), 0.8)
        self.assertEqual(state.panel(typed + 1.0)["foot"], [("Tab", "rewrite"), ("Enter", "ask")])  # a pause
        self.assertEqual(state.hint(typed + 1.0), "Tab rewrite · Enter ask")
        state.submit()
        working = state.panel()
        self.assertEqual((working["status"], working["busy"], working["foot"]), ("Working", True, [("Esc", "stop")]))
        state.offer(state.revision, "Hi!", ["Hello!", "Hey!"], hosted="Claude")
        drafts = state.panel()
        self.assertEqual(([r["text"] for r in drafts["rows"]], drafts["on"]), (["Hi!", "Hello!", "Hey!"], 0))
        self.assertEqual((drafts["foot"], drafts["mark"]), ([("1–3", "pick"), ("Esc", "back")], "from Claude · hosted"))
        state.change("this is important")
        state.tab()
        state.offer(state.revision, "This is crucial.")
        rewritten = state.panel()  # your words, as large, until you keep it
        self.assertEqual((rewritten["label"], rewritten["body"], rewritten["mark"]), ("Your words", "this is important", ""))
        state.change("x")
        state.submit()
        state.fail(state.revision, "Connection refused")
        failed = state.panel()
        self.assertEqual((failed["tile"], failed["failed"]), ("warn", "The model is offline"))
        state.change("y")
        state.submit()
        state.ask(state.revision, {"id": "q", "text": "The model asks: Did you mean git status?",
                                   "choices": [{"label": "Yes"}, {"label": "No"}]}, "s")
        asked = state.panel()  # no label sent: split from the text
        self.assertEqual((asked["label"], asked["body"], asked["on"], asked["tail"]),
                         ("The model asks", "Did you mean git status?", 0, "or type a reply"))
        state.ask(state.revision, {"id": "p", "text": "Allow Bash?", "permission": True, "label": "Claude Code wants to run",
                                   "body": "git push", "code": True, "choices": [{"label": "Deny"}, {"label": "Allow"}]}, "s")
        approval = state.panel()  # nothing highlighted; typed words only refuse
        self.assertEqual((approval["body"], approval["code"], approval["on"], approval["tail"]),
                         ("git push", True, -1, "or type why not"))

    def test_a_leading_space_is_the_apps_not_the_compositions(self):
        state = Composition()
        state.mode = "compose"
        self.assertTrue(state.passes(" "))  # after the previous word: straight into the app
        for char in ".,:;!?\"'(-":
            self.assertTrue(state.passes(char), char)  # punctuation too
        for char in "a7é日":
            self.assertFalse(state.passes(char), char)  # letters and digits start a composition
        state.insert("h")
        self.assertFalse(state.passes(" "))  # inside a phrase it is part of it
        state.mode = "continue"
        state.change("")
        self.assertFalse(state.passes(" "))  # continue types everything into the app anyway

    def test_rewrite_esc_while_asking_stops_and_keeps_your_words(self):
        state = Composition()
        state.mode = "compose"
        state.change("very good")
        state.tab()
        revision = state.revision
        self.assertEqual((state.escape(), state.text, state.working), ("back", "very good", False))
        self.assertFalse(state.offer(revision, "Late."))  # the stopped request's answer is ignored

    def test_rewrite_backspace_after_converting_is_your_words_again(self):
        state = Composition()
        state.mode = "compose"
        state.change("hi")
        state.tab()
        state.offer(state.revision, "Hello.")
        state.backspace()
        self.assertEqual((state.shown, state.text, state.candidate), ("hi", "hi", "Hello."))

    def test_instruct_esc_closes_the_drafts_then_drops_the_instruction(self):
        state = Composition()
        state.mode = "compose"
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


class AgentReplyTests(unittest.TestCase):
    def test_typing_while_an_agent_asks_composes_a_reply(self):
        state = Composition()
        state.mode = "compose"
        state.change("is my branch clean")
        state.submit()
        revision = state.revision
        state.ask(revision, {"id": "q1", "text": "Allow Bash?", "choices": [{"label": "Allow"}, {"label": "Deny"}],
                             "permission": True}, "s1")
        self.assertEqual(state.enter(), "wait")  # nothing typed yet: Enter waits
        for char in "use 2 diffs":
            state.insert(char)
        self.assertEqual((state.text, state.shown, state.revision), ("is my branch clean", "use 2 diffs", revision))
        self.assertIsNone(state.answer_choice(2))  # a digit inside a reply is text
        state.backspace()
        self.assertEqual(state.escape(), "clear")  # Esc clears the reply; the question stays
        self.assertTrue(state.question and not state.reply)
        for char in "use git diff":
            state.insert(char)
        self.assertEqual(state.enter(), "reply")
        self.assertEqual(state.answer_text(), ("s1", "q1", "use git diff"))
        self.assertIsNone(state.question)
        self.assertTrue(state.working)  # the agent carries on with your words


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
        state.toggle()  # compose asks on Tab or Enter, not on pauses
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
