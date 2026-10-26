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
        state.submit()  # Enter: an instruction
        return state

    def test_a_click_takes_a_draft_only_from_an_instructions_list(self):
        state = Composition()
        state.insert("I have")
        state.offer(state.revision, "I possess", ["I hold"])
        self.assertIsNone(state.click(1))  # while typing there are no rows ("2" is text)
        state = self.instruct()
        state.offer(state.revision, "One.", ["Two.", "One.", ""])
        self.assertEqual(state.candidates, ["One.", "Two."])  # deduplicated, empties dropped
        self.assertIsNone(state.click(2))
        self.assertEqual(state.click(1), "accept")  # the second row: highlighted, then taken as Tab takes it
        self.assertEqual(state.commit(True), "Two.")
        self.assertEqual((state.text, state.candidates), ("", []))

    def test_typing_while_it_works_keeps_the_work_and_a_stale_list_is_dropped(self):
        state = self.instruct()
        revision = state.revision
        state.insert("y")  # your next words take the instruction's place in the composition; the work goes on
        self.assertEqual((state.shown, state.reply), ("y", "y"))
        self.assertTrue(state.offer(revision, "One.", ["Two."]))
        self.assertTrue(state.panel()["rows"] and state.panel()["replying"])  # the drafts fade while you type
        self.assertEqual(state.escape(), "clear")  # Esc: your next words go
        self.assertEqual(state.escape(), "back")  # Esc again: the instruction comes back to edit
        self.assertFalse(state.offer(revision, "Late.", []))  # a late answer for it is dropped
        self.assertEqual(state.panel()["rows"], [])


class SummonKeyTests(unittest.TestCase):
    """By default Enter puts your words in and Shift+Enter sends them to the model; "keys":
    {"summon": "Enter"} swaps them. Once the model is asked, the keeper key does nothing."""

    def composing(self, summon):
        state = Composition()
        state.mode, state.summon = "compose", summon
        state.change("running late")
        return state

    def test_enter_asks_when_set_so(self):
        state = self.composing("Enter")
        self.assertEqual((state.talks(False), state.talks(True)), (True, False))
        self.assertEqual(state.panel()["foot"], [("Tab", "rewrite"), ("Enter", "ask"), ("Shift+Enter", "keep")])

    def test_by_default_shift_enter_asks_and_enter_keeps(self):
        self.assertEqual(Composition().summon, "Shift+Enter")
        state = self.composing("Shift+Enter")
        self.assertEqual((state.talks(False), state.talks(True)), (False, True))
        self.assertEqual(state.panel()["foot"], [("Tab", "rewrite"), ("Shift+Enter", "ask"), ("Enter", "keep")])
        state.offline = True
        self.assertEqual(state.panel()["foot"], [("Enter", "keep")])

    def test_one_key_talks_to_the_model_throughout(self):
        """Owner: the first instruction with Shift+Enter and follow-ups with Enter was the quirk."""
        state = self.composing("Shift+Enter")
        state.submit()
        state.offer(state.revision, "Sorry, running late.")
        self.assertEqual((state.talks(False), state.talks(True)), (False, True))
        self.assertIsNone(state.keep())  # a reflexive Enter on drafts: nothing goes in, Tab lights
        self.assertTrue(state.panel()["nudge"])
        state.question = {"text": "Which day?", "choices": [{"label": "Friday"}]}
        panel = state.panel()
        self.assertEqual(panel["foot"][-1], ("Tab", "confirm"))  # Tab takes a choice
        state.insert("Monday")  # a reply: Shift+Enter sends it; Enter is gated once the model is summoned
        self.assertEqual(state.panel()["foot"][0], ("Shift+Enter", "send reply"))
        self.assertIsNone(state.keep())
        self.assertEqual(state.enter(), "reply")

    def test_one_draft_takes_the_arrows_without_moving(self):
        """On the Mac VM, ↓ on a single draft went to the app and ended the exchange."""
        state = self.composing("Shift+Enter")
        state.submit()
        state.offer(state.revision, "Sorry, I can't make the offsite.")
        self.assertTrue(state.move(1) and state.move(-1))
        self.assertEqual((state.highlight, state.tab()), (0, "accept"))

    def test_a_rewrite_on_its_way_or_shown_gates_enter_too(self):
        state = self.composing("Shift+Enter")
        self.assertEqual(state.tab(), "request")  # the spinner: a reflexive Enter must not send
        self.assertIsNone(state.keep())
        state.offer(state.revision, "Running slightly behind.")
        self.assertIsNone(state.keep())  # the rewrite waits for Tab; Esc first to keep your words
        self.assertEqual((state.escape(), state.keep()), ("back", "running late"))
        state = self.composing("Shift+Enter")
        state.tab()
        state.fail(state.revision, "offline")
        self.assertEqual(state.keep(), "running late")  # nothing from the model waits: Enter keeps


class ReceiveTests(unittest.TestCase):
    """The worker's results, dispatched once for every adapter; each draws the kind its own way."""

    def test_each_kind_and_stale_results(self):
        state = Composition()
        state.mode = "compose"
        state.change("say thanks")
        state.submit()
        self.assertIsNone(state.receive(state.revision - 1, {"text": "old"}))  # stale: nothing changes
        self.assertEqual(state.receive(state.revision, {"progress": "reading"}), "progress")
        self.assertEqual(state.receive(state.revision, {"question": {"id": "q", "text": "Which?", "body": "Which?",
                                                                     "choices": [{"label": "A"}]}, "session": "s"}), "question")
        state.answer_choice()
        self.assertEqual(state.receive(state.revision, {"text": "Thanks—truly.", "candidates": ["Thanks—truly."]}), "text")
        self.assertIsNone(state.receive(state.revision, {"error": "late"}))  # it finished: nothing changes
        state.change("say thanks again")
        state.submit()
        self.assertEqual(state.receive(state.revision, {"error": "boom"}), "error")

    def test_a_failed_instruction_drops_its_queued_questions(self):
        state = Composition()
        state.mode = "compose"
        state.change("deploy")
        state.submit()
        for qid in ("a", "b"):
            state.ask(state.revision, {"id": qid, "text": qid, "body": qid, "choices": [{"label": "ok"}]}, "s")
        state.fail(state.revision, "timed out")
        self.assertEqual(state.queued, [])  # a retry does not show the dead session's next question

    def test_restore_keeps_the_fields_and_services_state_of_now(self):
        state = Composition()
        state.mode = "compose"
        state.change("decline politely")
        state.submit()
        state.leave("mail")
        state.field(terminal=True)
        state.hints = False
        state.restore()
        self.assertTrue(state.sent)  # the exchange is back
        self.assertEqual((state.terminal, state.hints), (True, False))  # where the caret is now, the config now

    def test_follow_copies_the_workers_view(self):
        state, worker = Composition(), type("W", (), {"summon": "Enter", "hints": False, "offline": True})()
        self.assertTrue(state.follow(worker))
        self.assertEqual((state.summon, state.hints, state.offline), ("Enter", False, True))
        self.assertFalse(state.follow(worker))  # nothing changed


class HintsTests(unittest.TestCase):
    """"hints": false: no keys while you compose, no toasts; the panel while something is pending
    (working, or drafts, a rewrite, a question waiting on Tab) or went wrong."""

    def quiet(self):
        state = Composition()
        state.mode, state.hints = "compose", False
        state.change("running late")
        return state

    def test_composing_shows_nothing_and_working_and_failures_show(self):
        state = self.quiet()
        self.assertIsNone(state.panel())
        self.assertIsNone(state.toast())
        self.assertIsNone(state.dropped_toast())
        state.submit()
        self.assertTrue(state.panel()["busy"])  # pending: it works on what you asked
        state.fail(state.revision, "no model")
        self.assertTrue(state.panel()["failed"])  # errors show, hints or not
        state = self.quiet()
        state.offline = True
        self.assertEqual(state.panel()["failed"], "cd_AI is offline")

    def test_drafts_a_rewrite_and_questions_still_show(self):
        state = self.quiet()
        state.submit()
        state.offer(state.revision, "Running late.", ["Running late—apologies."])
        self.assertEqual(len(state.panel()["rows"]), 2)
        state = self.quiet()
        self.assertEqual(state.tab(), "request")
        self.assertTrue(state.panel()["busy"])
        state.offer(state.revision, "I am running late.")
        self.assertEqual(state.panel()["body"], "I am running late.")
        state = self.quiet()
        state.submit()
        state.ask(state.revision, {"id": "q", "text": "Which meeting?", "choices": [{"label": "Standup"}]}, "s")
        self.assertEqual(state.panel()["rows"][0]["text"], "Standup")

    def test_a_drop_in_a_terminal_says_nothing(self):
        state = Composition()
        self.assertTrue(state.dropped_toast())
        state.terminal = True  # Terminal.app keeps Esc from an input method when nothing is marked
        self.assertIsNone(state.dropped_toast())

    def test_by_default_hints_show(self):
        state = Composition()
        state.change("running late")
        self.assertTrue(state.hints)
        self.assertTrue(state.panel()["foot"])
        self.assertTrue(state.toast())


class ModeFeelTests(unittest.TestCase):
    """Each mode looks different at the caret: a rewrite waits in the panel, an instruction lists drafts."""

    def test_tab_shows_a_rewrite_and_esc_steps_back(self):
        state = Composition()
        state.mode = "compose"
        state.change("very good")
        self.assertEqual(state.tab(), "request")  # Tab asks for the rewrite
        self.assertEqual(state.tab(), "wait")  # asked already
        state.offer(state.revision, "Exceptionally good.")
        self.assertEqual(state.panel()["rows"], [])  # no list for a rewrite
        # Your words stay the composition; the rewrite shows in the panel, and only Tab takes it
        # (a focus change, which apps turn into a commit, can never insert the model's words).
        self.assertEqual(state.shown, "very good")
        self.assertEqual((state.panel()["label"], state.panel()["body"]), ("Rewrite", "Exceptionally good."))
        self.assertEqual((state.escape(), state.shown, state.panel()["label"]), ("back", "very good", None))
        self.assertEqual(state.tab(), "request")  # owner: Esc, then Tab, is another take
        state.offer(state.revision, "Exceptionally, remarkably good.")
        self.assertEqual((state.enter(), state.tab()), ("wait", "accept"))  # Tab keeps it; Enter does not
        self.assertEqual(state.commit(True), "Exceptionally, remarkably good.")
        state.change("very good")
        state.tab()
        state.offer(state.revision, "Exceptionally good.")
        self.assertEqual(state.commit(), "very good")  # a commit without Tab (a focus change): your words

    def test_esc_steps_back_until_what_you_composed_is_dropped(self):
        state = Composition()
        state.mode = "compose"
        state.change("very good")
        state.tab()
        state.offer(state.revision, "Exceptionally good.")
        self.assertEqual([state.escape() for _ in range(3)], ["back", "drop", "pass"])

    def test_shift_keeps_what_you_see_and_goes_to_continue(self):
        state = Composition()
        self.assertEqual(state.mode, "compose")  # where cd_AI starts
        state.change("very good")
        self.assertEqual((state.toggle(), state.mode, state.text), ("very good", "continue", "very good"))
        self.assertEqual((state.toggle(), state.mode, state.text), ("", "compose", ""))
        state.change("hi")
        state.tab()
        state.offer(state.revision, "Hello.")
        self.assertEqual(state.toggle(), "hi")  # your words: a rewrite in the panel goes in only with Tab

    def test_the_keeper_keeps_it_as_it_is_and_stays_in_compose(self):
        state = Composition()
        state.mode = "compose"
        self.assertEqual(state.keep(), "")  # nothing composed: Enter is the app's
        state.change("as typed")
        self.assertEqual((state.keep(), state.mode, state.text), ("as typed", "compose", ""))

    def test_the_summon_key_sends_an_instruction_and_tab_a_rewrite(self):
        state = Composition()
        state.mode = "compose"
        state.change("decline politely")
        self.assertEqual(state.enter(), "submit")
        state.submit()
        self.assertEqual(state.asked, "instruct")
        state.offer(state.revision, "No, thank you.", ["Sadly, no."])
        self.assertEqual(len(state.panel()["rows"]), 2)  # an instruction's drafts are a list
        self.assertEqual(state.tab(), "accept")  # Tab takes the highlighted draft
        state.change("decline politely")
        state.tab()
        self.assertEqual(state.asked, "rewrite")

    def test_a_space_keeps_the_drafts_and_a_quick_enter_waits(self):
        """Poll (a pinyin user): a reflexive Space must not throw away drafts you waited for, and a
        double-tapped Enter must not insert one nobody read."""
        state = Composition()
        state.mode = "compose"
        state.change("decline politely")
        state.submit()
        state.offer(state.revision, "No, thank you.", ["Sadly, no."])
        self.assertEqual(state.enter(), "wait")  # right after the drafts appear
        self.assertEqual(state.shown, "decline politely")  # sent: it stays the composition while choices show
        state.insert(" ")
        self.assertEqual(len(state.panel()["rows"]), 2)  # a Space with nothing typed does nothing; the drafts stay
        self.assertEqual(state.shown, "decline politely")  # and types nothing
        self.assertEqual((state.move(1), state.tab(), state.commit(True)), (True, "accept", "Sadly, no."))
        state.change("decline politely")
        state.submit()
        state.offer(state.revision, "No, thank you.", ["Sadly, no."])
        state.insert("m")
        state.insert("o")  # letters are your next words, at the caret; the drafts stay, without numbers
        self.assertTrue(state.panel()["rows"] and state.panel()["replying"])
        self.assertEqual((state.shown, state.text), ("mo", "decline politely"))
        self.assertEqual(state.enter(), "submit")  # the summon key asks it as a follow-up
        self.assertEqual((state.text, state.reply, state.candidates), ("mo", "", []))
        state.submit()
        state.offer(state.revision, "No, thank you.")
        # Tab takes the model's text; Enter only talks to the model, so a reflexive second Enter
        # after sending can never insert a draft nobody read (owner, 2026-10-24).
        self.assertEqual((state.enter(), state.tab()), ("wait", "accept"))

    def test_a_key_that_does_nothing_on_a_choice_lights_its_tab(self):
        """Owner: Enter on the approval lit nothing, where on drafts it lights Tab."""
        state = Composition()
        state.mode = "compose"
        state.change("hand it over")
        state.submit()
        state.ask(state.revision, {"id": "p", "text": "Send this task to claude?", "permission": True,
                                   "choices": [{"label": "Deny"}, {"label": "Allow"}]}, "s")
        before = state.panel()
        self.assertIsNone(state.keep())
        self.assertFalse(state.panel()["nudge"])  # nothing highlighted: nothing to light
        import copy
        probe = copy.deepcopy(state)
        probe.move(1)
        # Owner: the panel grew on ↓ (the key's column and "Tab confirm" appeared): both are there from the start.
        self.assertEqual((before["column"], before["foot"]), (True, probe.panel()["foot"]))
        state.move(1)  # ↓: Deny
        self.assertIsNone(state.keep())
        self.assertTrue(state.panel()["nudge"])  # Enter lights the highlighted row's Tab
        state.move(1)  # ↓: Allow, a change: the light goes
        self.assertFalse(state.panel()["nudge"])
        self.assertEqual(state.enter(), "wait")  # Shift+Enter with nothing typed lights it too
        self.assertTrue(state.panel()["nudge"])

    def test_words_typed_while_it_works_survive_a_question_and_the_end(self):
        """Codex: a question, or the instruction finishing elsewhere, erased a follow-up being typed."""
        state = Composition()
        state.mode = "compose"
        state.change("summarize the thread")
        state.submit()
        for char in "also mention Friday":
            state.insert(char)
        state.ask(state.revision, {"id": "p", "text": "Send this task to claude?", "permission": True,
                                   "choices": [{"label": "No"}, {"label": "Yes"}]}, "s")
        shown = state.panel()
        self.assertEqual((state.reply, shown["thread"][-1]), ("", {"label": "Waiting", "body": "also mention Friday"}))
        self.assertEqual(shown["foot"][0], ("↑↓", "choose"))  # not "deny with reason": they are not an answer
        state.move(1)
        self.assertEqual(state.answer_choice(), ("s", "p", 0))
        self.assertEqual(state.reply, "also mention Friday")  # back at the caret, for Shift+Enter
        self.assertEqual(state.enter(), "submit")  # the follow-up, in the same conversation
        state.submit()
        for char in "and Monday":
            state.insert(char)
        self.assertTrue(state.done(state.revision))  # a helper took it: your words stay, unsent
        self.assertEqual((state.text, state.sent, state.reply), ("and Monday", False, ""))

    def test_tab_on_an_answer_to_read_keeps_the_waiting_follow_up(self):
        """Codex: the answer went in with Tab and the follow-up waiting beside it disappeared."""
        state = Composition()
        state.mode = "compose"
        state.change("what does this error mean")
        state.submit()
        for char in "then fix it":
            state.insert(char)
        state.ask(state.revision, {"id": "r", "read": True, "label": "The model says", "body": "A quote is open.",
                                   "insert": "A quote is open.", "choices": [{"label": "Insert it"}, {"label": "Dismiss"}]}, "s")
        self.assertEqual(state.tab(), "accept")
        self.assertEqual(state.commit(True), "A quote is open.")
        self.assertEqual((state.text, state.sent), ("then fix it", False))  # the next composition, unsent

    def test_a_second_question_waits_for_the_first(self):
        """Codex: a second permission request replaced the first, which stayed pending on the server."""
        state = Composition()
        state.mode = "compose"
        state.change("tidy the repo")
        state.submit()
        first = {"id": "p1", "text": "Allow git.add?", "permission": True, "choices": [{"label": "Deny"}, {"label": "Allow"}]}
        second = dict(first, id="p2", text="Allow git.commit?")
        state.ask(state.revision, first, "s")
        state.ask(state.revision, second, "s")
        self.assertEqual(state.question["id"], "p1")  # one at a time
        state.move(1)
        self.assertEqual(state.answer_choice(), ("s", "p1", 0))
        self.assertEqual((state.question["id"], state.selected), ("p2", False))  # the next, nothing highlighted
        state.move(1)
        self.assertEqual(state.answer_choice(), ("s", "p2", 0))
        self.assertIsNone(state.question)

    def test_tab_takes_the_first_choice_of_a_question_but_never_approves(self):
        state = Composition()
        state.mode = "compose"
        state.change("fix")
        state.submit()
        state.ask(state.revision, {"id": "q", "text": "The model asks: Did you mean git status?",
                                   "choices": [{"label": "Yes"}, {"label": "No"}]}, "s")
        self.assertEqual((state.enter(), state.tab()), ("wait", "choose"))  # Tab takes what the model offers
        state.answer_choice()
        state.ask(state.revision, {"id": "p", "text": "Allow notes.delete?", "permission": True,
                                   "choices": [{"label": "Allow"}, {"label": "Deny"}]}, "s")
        self.assertEqual(state.tab(), "wait")  # an approval needs a highlighted choice (↓ first)
        self.assertEqual(state.enter(), "wait")

    def test_continue_waits_for_the_end_of_a_line(self):
        state = Composition()
        state.mode = "continue"
        state.change("Thanks for the review ")
        self.assertTrue(state.automatic)
        state.inside = True  # text follows the caret on its line
        self.assertFalse(state.automatic)
        state.inside, state.quiet = False, True  # a number field
        self.assertFalse(state.automatic)

    def test_the_panel_is_the_labs_and_the_keys_wait_for_a_pause(self):
        """Composition.panel() is what every adapter draws (docs/design/design.md): one header,
        rows with the highlighted one, one footer of keys with their verbs."""
        state = Composition()
        self.assertIsNone(state.panel())  # continue: no panel; the suggestion speaks for itself
        state.mode = "compose"
        state.change("say hi")
        # What each Enter does shows from the first key (CJK reviewers: Enter must not surprise).
        self.assertEqual(state.panel()["foot"], [("Tab", "rewrite"), ("Shift+Enter", "ask"), ("Enter", "keep")])
        self.assertEqual(state.hint(), "Tab rewrite · Shift+Enter ask · Enter keep")
        state.submit()
        working = state.panel()
        self.assertEqual((working["status"], working["busy"], working["foot"]), ("working", True, [("Esc", "stop")]))
        state.offer(state.revision, "Hi!", ["Hello!", "Hey!"])
        drafts = state.panel()
        self.assertEqual(([r["text"] for r in drafts["rows"]], drafts["on"]), (["Hi!", "Hello!", "Hey!"], 0))
        self.assertEqual(drafts["foot"], [("↑↓", "choose"), ("Tab", "insert"), ("Esc", "edit")])
        self.assertEqual(drafts["thread"], [])  # the instruction is still the composition: no "You asked"
        state.change("this is important")
        state.tab()
        state.offer(state.revision, "This is crucial.")
        rewritten = state.panel()  # your words, as large, until you keep it
        self.assertEqual((rewritten["label"], rewritten["body"]), ("Rewrite", "This is crucial."))
        state.change("x")
        state.submit()
        state.fail(state.revision, "Connection refused")
        failed = state.panel()
        self.assertEqual((failed["tile"], failed["failed"]), ("warn", "the model is offline"))
        state.change("y")
        state.submit()
        state.ask(state.revision, {"id": "q", "text": "Did you mean git status?", "label": "The model asks",
                                   "body": "Did you mean git status?", "choices": [{"label": "Yes"}, {"label": "No"}]}, "s")
        asked = state.panel()
        self.assertEqual((asked["label"], asked["body"], asked["on"], asked["tail"]),
                         ("The model asks", "Did you mean git status?", 0, "or type a reply"))
        state.answer_choice()  # answered: the next question shows (they come one at a time)
        state.ask(state.revision, {"id": "p", "text": "Allow Bash?", "permission": True, "label": "Claude Code wants to run",
                                   "body": "git push", "code": True, "choices": [{"label": "Deny"}, {"label": "Allow"}]}, "s")
        approval = state.panel()  # nothing highlighted; typed words only refuse
        self.assertEqual((approval["body"], approval["code"], approval["on"], approval["tail"]),
                         ("git push", True, -1, "or type why not"))

    def test_an_answer_to_read_goes_in_with_tab_and_esc_dismisses_it(self):
        state = Composition()
        state.mode = "compose"
        state.change("what does this error mean")
        state.submit()
        read = {"id": "r", "read": True, "label": "The model says", "body": "A quote is open.\nClose it.",
                "insert": "A quote is open. Close it.", "choices": [{"label": "Insert it"}, {"label": "Dismiss"}]}
        state.ask(state.revision, dict(read), "s")
        shown = state.panel()
        self.assertEqual((shown["rows"], shown["foot"]), ([], [("Tab", "insert"), ("Esc", "dismiss")]))
        self.assertEqual(state.escape(), "dismiss")
        # Tab: what you read goes in now (its insertable form), "Insert it" goes back to be recorded,
        # and no second answer is waited for (owner: it took a second Tab).
        state.ask(state.revision, dict(read), "s")
        self.assertEqual((state.enter(), state.tab()), ("wait", "accept"))
        self.assertEqual((state.take_answering(), state.take_answering()), (("s", "r", 0), None))
        self.assertEqual(state.commit(True), "A quote is open. Close it.")

    def test_enter_on_the_models_text_lights_tab_until_the_next_key(self):
        """Round 5 (seven reviewers): Enter never inserts the model's text, but a key that does
        nothing must say why. Enter on drafts lights the highlighted row's Tab, the key that takes
        it; any key that changes the panel ends it; nothing is inserted or sent again. A rewrite
        or an answer has no row: its footer says Tab insert, and nothing is lit (owner)."""
        state = Composition()
        state.mode = "compose"
        state.change("decline politely")
        state.submit()
        state.offer(state.revision, "No, thank you.", ["I can't, sorry."])
        self.assertFalse(state.panel()["nudge"])
        self.assertEqual(state.enter(), "wait")
        self.assertTrue(state.panel()["nudge"])
        self.assertEqual(state.enter(), "wait")  # again: still lit, still nothing inserted
        self.assertTrue(state.panel()["nudge"])
        state.move(1)  # ↓: the panel changed, so the light ends
        self.assertFalse(state.panel()["nudge"])

        early = Composition()  # a reflexive Enter before the drafts arrive: Tab lights when they do
        early.mode = "compose"
        early.change("say hi")
        early.submit()
        self.assertEqual(early.enter(), "wait")
        early.offer(early.revision, "Hi!", ["Hello!"])
        self.assertTrue(early.panel()["nudge"])
        typed = Composition()  # but not once you typed on
        typed.mode = "compose"
        typed.change("say hi")
        typed.submit()
        typed.enter()
        typed.insert("x")
        typed.offer(typed.revision, "Hi!")
        self.assertFalse((typed.panel() or {}).get("nudge"))

        rewrite = Composition()
        rewrite.mode = "compose"
        rewrite.change("this is very important")
        rewrite.tab()
        rewrite.offer(rewrite.revision, "This is crucial.")
        self.assertEqual(rewrite.panel()["foot"], [("Tab", "insert"), ("Esc", "dismiss")])  # not "keep" / "undo"
        self.assertEqual(rewrite.enter(), "wait")
        self.assertFalse(rewrite.panel()["nudge"])

        answer = Composition()
        answer.mode = "compose"
        answer.change("what does this mean")
        answer.submit()
        answer.ask(answer.revision, {"id": "r", "read": True, "label": "The model says", "body": "A quote is open.",
                                     "choices": [{"label": "Insert it"}, {"label": "Dismiss"}]}, "s")
        self.assertEqual(answer.enter(), "wait")
        self.assertFalse(answer.panel()["nudge"])

    def test_choices_are_not_numbered_and_an_approval_starts_unhighlighted(self):
        """Owner: digits are text in English, as Space is; "2 + Tab" and "↓ + Tab" are both two
        strokes. Choices are chosen with ↑/↓ and Tab; an approval starts with nothing
        highlighted, the first ↓ lands on Deny, and a reply starting with a digit is just a reply."""
        state = Composition()
        state.mode = "compose"
        state.change("push my branch")
        state.submit()
        state.ask(state.revision, {"id": "p", "permission": True, "label": "Claude Code wants to run", "body": "git push",
                                   "code": True, "choices": [{"label": "Deny"}, {"label": "Allow"}]}, "s")
        approval = state.panel()
        self.assertEqual((approval["on"], [r["text"] for r in approval["rows"]], state.tab()), (-1, ["Deny", "Allow"], "wait"))
        self.assertTrue(state.move(1))  # the first ↓: Deny
        self.assertEqual(state.panel()["on"], 0)
        self.assertTrue(state.move(1))  # ↓ again: Allow, then Tab confirms
        self.assertEqual((state.tab(), state.answer_choice()), ("choose", ("s", "p", 1)))
        state.ask(state.revision, {"id": "q", "permission": True, "choices": [{"label": "Deny"}, {"label": "Allow"}]}, "s")
        state.insert("2")  # a digit is text: your reply ("2 tests are flaky"), never an approval
        self.assertEqual((state.shown, state.panel()["foot"][0]), ("2", ("Shift+Enter", "deny with reason")))

    def test_esc_says_what_it_dropped_and_shift_esc_restores_a_reply(self):
        state = Composition()
        state.mode = "compose"
        state.change("summarize")
        state.submit()
        state.insert("o")
        state.insert("k")
        self.assertEqual(state.escape(), "clear")
        self.assertIsNone(state.dropped_toast())  # the question's panel stays: no toast over it
        self.assertEqual((state.restore(), state.shown), ("ok", "ok"))  # the reply, back at the caret
        fresh = Composition()
        fresh.mode = "compose"
        fresh.change("say hi")
        self.assertEqual(fresh.escape(), "drop")
        self.assertEqual(fresh.dropped_toast()["foot"], [("Shift+Esc", "restore")])

    def test_after_sending_the_keys_follow_one_ladder(self):
        """docs/design/design.md: ↑/↓ move the highlight (digits are text); Esc cancels what you
        typed, then edits, then drops (named in the footer); Shift+Esc brings a dropped
        instruction back."""
        state = Composition()
        state.mode = "compose"
        state.change("summarize this thread")
        state.submit()
        self.assertEqual(state.shown, "summarize this thread")  # it stays the composition until you type a reply
        state.ask(state.revision, {"id": "q", "label": "The model asks", "body": "All, or the last?",
                                   "choices": [{"label": "All"}, {"label": "The last"}]}, "s")
        self.assertEqual(state.panel()["thread"], [])  # the composition at the caret says what you asked
        self.assertTrue(state.move(1) and state.panel()["on"] == 1 and state.highlight == 1)  # ↓
        state.insert("3")
        state.insert(" ")
        state.insert("days")
        self.assertEqual((state.shown, state.panel()["replying"]), ("3 days", True))  # digits are text
        self.assertEqual(state.panel()["foot"], [("Shift+Enter", "send reply"), ("Esc", "cancel reply")])
        self.assertFalse(state.move(1))  # typing: nothing is highlighted
        self.assertEqual(state.answer_text()[2], "3 days")
        self.assertEqual(state.panel()["thread"][-1], {"label": "You answered", "body": "3 days"})
        self.assertEqual(state.escape(), "back")  # while it works: Esc edits (and stops it)
        self.assertEqual((state.shown, state.panel()["foot"][-1]), ("summarize this thread", ("Esc", "drop")))
        self.assertEqual(state.escape(), "drop")
        self.assertEqual((state.text, state.restore()), ("", "summarize this thread"))  # Shift+Esc
        self.assertEqual(state.shown, "summarize this thread")

    def test_a_shift_tap_holds_a_sent_exchange_for_shift_esc(self):
        state = Composition()
        state.change("decline politely")
        state.submit()
        state.offer(state.revision, "A draft.", ["Another."])
        self.assertEqual((state.toggle(), state.mode), ("", "continue"))  # the instruction is not text for the app
        state.toggle()  # back to compose
        self.assertEqual(state.restore(), "decline politely")  # Shift+Esc: the exchange, drafts and all
        self.assertEqual(state.candidates, ["A draft.", "Another."])

    def test_returning_to_a_failed_exchange_keeps_its_reason(self):
        state = Composition()
        state.change("explain this")
        state.submit()
        sent = state.revision
        self.assertEqual(state.leave("app"), "")
        state.fail(sent, "no Claude credentials: save a key in Settings")
        self.assertEqual(state.returned("app")["status"], "no Claude key yet")
        self.assertEqual(state.returned("app")["foot"], [("Shift+Esc", "open")])
        self.assertEqual(state.text, "")

    def test_a_focus_change_commits_only_your_own_words(self):
        """Seven reviewers, unanimous: a focus change may commit your own words, never the model's,
        never words meant for the model, and it never sends or approves."""
        state = Composition()
        state.mode = "compose"
        state.change("very good")
        state.tab()
        state.offer(state.revision, "Exceptionally good.")
        self.assertEqual(state.leave("app"), "very good")  # your words, not the rewrite
        state.change("summarize this")
        state.submit()
        sent = state.revision
        state.ask(sent, {"id": "q", "label": "The model asks", "body": "All?", "choices": [{"label": "Yes"}]}, "s")
        state.insert("o")
        state.insert("n")
        self.assertEqual(state.leave("app"), "")  # words for the model never go into the app: held with the exchange
        self.assertIsNone(state.returned("other app"))  # never offered in another app
        self.assertEqual(state.returned("app")["status"], "the model asks")  # a pill, taking no keys
        self.assertEqual((state.text, state.panel()), ("", None))
        state.note(sent, "Reading")  # results for the exchange you left go to it
        self.assertEqual(state.restore(), "on")  # Shift+Esc: it is back, your unsent reply at the caret
        self.assertEqual((state.shown, state.question["id"], state.status), ("on", "q", "Reading"))

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

    def test_arrows_move_in_what_you_type_and_edits_land_at_the_cursor(self):
        state = Composition()
        state.mode = "compose"
        for char in "thanks team":
            state.insert(char)
        self.assertTrue(all(state.arrow(-1) for _ in range(20)))  # past the start: stays at it
        state.insert("A")
        self.assertEqual((state.text, state.cursor), ("Athanks team", 1))
        state.arrow(1)
        state.backspace()
        state.delete()
        self.assertEqual((state.text, state.cursor), ("Aanks team", 1))  # the t before, the h after
        state.submit()  # sent: your next words start at the end
        for char in "shorter":
            state.insert(char)
        state.arrow(-1)
        state.insert("!")
        self.assertEqual((state.reply, state.cursor), ("shorte!r", 7))
        self.assertFalse(Composition().arrow(-1))  # nothing typed: the key is the app's

    def test_a_follow_up_is_about_the_draft_in_view(self):
        state = Composition()
        state.mode = "compose"
        state.change("three ways to say no")
        state.submit()
        state.offer(state.revision, "No—respectfully.", ["No—respectfully.", "Alas, no.", "Not this time."])
        state.move(1)
        for char in "shorter":
            state.insert(char)
        panel = state.panel()
        self.assertEqual((panel["on"], panel["replying"]), (1, True))  # the draft in view stays highlighted
        self.assertEqual((state.enter(), state.text, state.about), ("submit", "shorter", "Alas, no."))
        state.submit()
        state.offer(state.revision, "No.")
        for char in "warmer":
            state.insert(char)
        self.assertEqual((state.enter(), state.about), ("submit", "No."))  # one draft: in view all the same
        state.submit()
        state.offer(state.revision, "No—kindly.")


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
        self.assertIsNone(state.answer_choice(1))  # while you type a reply, choices answer nothing
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
        state.mode = "continue"
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
        rewriter.modes["instruct"]["candidates"] = 3  # a template asking for three readings
        self.assertEqual(rewriter.rewrite("say hi", mode="instruct")["candidates"],
                         ["As requested—say hi.", "Certainly—as requested—say hi.", "Of course—as requested—say hi."])
        self.assertEqual(len(rewriter.rewrite("very good")["candidates"]), 1)

    def test_first_reading_is_deterministic_and_the_rest_sampled(self):
        rewriter = Rewriter()
        rewriter.modes["instruct"]["candidates"] = 3  # a template asking for three readings
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
        rewriter.modes["instruct"]["candidates"] = 3  # a template asking for three readings
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
            path.write_text(json.dumps({"profiles": {"p": {"templates": "words.json"}}}))
            for count, ok in ((1, True), (5, True), (0, False), (6, False), (True, False)):
                Path(directory, "words.json").write_text(json.dumps({"modes": {"instruct": {"candidates": count}}}))
                if ok:
                    _, settings, templates, _ = config.resolve(path)
                    self.assertEqual(Rewriter.from_settings(settings, templates).modes["instruct"]["candidates"], count)
                else:
                    with self.assertRaisesRegex(ValueError, "from 1 to 5"):
                        config.resolve(path)


if __name__ == "__main__":
    unittest.main()
