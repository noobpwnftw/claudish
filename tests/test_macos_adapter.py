"""Test routing with Cocoa/IMK test doubles; this is not native macOS validation."""
import builtins
import importlib.util
from pathlib import Path
import plistlib
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self):
        self.marked = ""
        self.selection = None
        self.commits = []

    def setMarkedText_selectionRange_replacementRange_(self, text, selection, replacement):
        self.marked = text
        self.selection = selection

    def insertText_replacementRange_(self, text, replacement):
        self.commits.append(text)
        self.marked = ""

    def bundleIdentifier(self):
        return "com.apple.TextEdit"


class TextClient(Client):
    """A client that shares its text, like NSTextView: the committed text plus the marked text."""

    def __init__(self, text):
        super().__init__()
        self.text = text

    def insertText_replacementRange_(self, text, replacement):
        super().insertText_replacementRange_(text, replacement)
        self.text += text

    def whole(self):
        marked = getattr(self.marked, "text", self.marked)
        return self.text + marked

    def length(self):
        return len(self.whole())

    def selectedRange(self):
        marked = getattr(self.marked, "text", self.marked)
        return (len(self.text) + (self.selection or (len(marked), 0))[0], 0)

    def markedRange(self):
        marked = getattr(self.marked, "text", self.marked)
        return (len(self.text), len(marked)) if marked else (2**63 - 1, 0)

    def attributedSubstringFromRange_(self, span):
        return types.SimpleNamespace(string=lambda: self.whole()[span[0]:span[0] + span[1]])

    def stringFromRange_actualRange_(self, span, actual):
        raise AssertionError("crashes in IMK when PyObjC passes a NULL actualRange")


class Grey:
    """NSAttributedString, as far as the adapter uses it."""

    @classmethod
    def alloc(cls):
        return cls()

    def initWithString_attributes_(self, text, attributes):
        self.text, self.attributes = text, attributes
        return self


class BaseController:
    def initWithServer_delegate_client_(self, server, delegate, client):
        self._client = client
        return self

    def client(self):
        return self._client

    def activateServer_(self, sender):
        pass

    def deactivateServer_(self, sender):
        pass


class Panel:
    @classmethod
    def alloc(cls):
        return cls()

    def initWithServer_panelType_(self, server, panel_type):
        self.visible = False
        return self

    def updateCandidates(self):
        pass

    def show_(self, hint):  # PyObjC's name for -show:; a plain show() does not exist on a real panel
        self.visible = True

    def hide(self):
        self.visible = False


class Timer:
    @classmethod
    def scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(cls, *args):
        return cls()

    def invalidate(self):
        self.invalidated = True


class Worker:
    def __init__(self):
        self.result = None
        self.closed = False
        self.modes = []

    def answer(self, session, question, choice=None, text=None):
        self.answered = (session, question, choice)

    def schedule(self, revision, text, mode="rewrite", immediate=False, app=None, look=False, before="", after=""):
        self.result = None
        self.modes.append(mode)
        self.sent = (text, before, after)
        self.app = app
        self.immediate = immediate
        self.look = look

    def poll(self):
        result, self.result = self.result, None
        return result

    def close(self):
        self.closed = True


def load_adapter():
    objc = types.ModuleType("objc")
    objc.super = builtins.super
    objc.python_method = lambda method: method
    objc.signature = lambda signature: lambda method: method
    appkit = types.ModuleType("AppKit")
    appkit.NSAttributedString = Grey
    appkit.NSColor = types.SimpleNamespace(secondaryLabelColor=lambda: "secondaryLabelColor")
    appkit.NSForegroundColorAttributeName = "NSColor"
    for name, value in {"NSEventMaskKeyDown": 1024, "NSEventTypeKeyDown": 10,
                        "NSEventModifierFlagCommand": 1 << 20,
                        "NSEventModifierFlagControl": 1 << 18,
                        "NSEventModifierFlagOption": 1 << 19}.items():
        setattr(appkit, name, value)
    foundation = types.ModuleType("Foundation")
    foundation.NSNotFound = 2**63 - 1
    foundation.NSTimer = Timer
    imk = types.ModuleType("InputMethodKit")
    imk.IMKInputController = BaseController
    imk.IMKCandidates = Panel
    imk.kIMKSingleColumnScrollingCandidatePanel = 1
    imk.kIMKLocateCandidatesBelowHint = 2
    spec = importlib.util.spec_from_file_location("claudish_macos_test", ROOT / "platforms/macos/controller.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", {"objc": objc, "AppKit": appkit,
                                     "Foundation": foundation, "InputMethodKit": imk}):
        spec.loader.exec_module(module)
    module.Suggestions = Worker
    return module


class MacOSAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_adapter()

    def setUp(self):
        self.client = Client()
        self.controller = self.module.ClaudishInputController().initWithServer_delegate_client_(
            object(), None, self.client)
        self.controller.activateServer_(None)
        self.controller.state.mode = "rewrite"  # these tests exercise rewrite; a new session starts in continue

    def tearDown(self):
        self.controller.inputControllerWillClose()

    def test_switching_to_cd_ai_types_like_en_us(self):
        fresh = self.module.ClaudishInputController().initWithServer_delegate_client_(object(), None, self.client)
        fresh.activateServer_(None)
        try:
            self.assertEqual(fresh.state.mode, "continue")
            for char in "ls -la":
                self.assertTrue(fresh.handleEvent_client_(types.SimpleNamespace(
                    type=lambda: 10, keyCode=lambda: 0, modifierFlags=lambda: 0, characters=lambda c=char: c), self.client))
            self.assertEqual("".join(self.client.commits), "ls -la")  # straight in; the hyphen stays a hyphen
            self.assertFalse(fresh.handleEvent_client_(types.SimpleNamespace(  # Tab with nothing offered is the app's
                type=lambda: 10, keyCode=lambda: 48, modifierFlags=lambda: 0, characters=lambda: "\t"), self.client))
        finally:
            fresh.inputControllerWillClose()

    def key(self, code, text="", flags=0):
        event = types.SimpleNamespace(type=lambda: 10, keyCode=lambda: code,
                                      modifierFlags=lambda: flags, characters=lambda: text)
        return self.controller.handleEvent_client_(event, self.client)

    def type_text(self, text):
        for char in text:
            self.assertTrue(self.key(0, char))

    def test_dash_utf16_ranges_and_pending_tab(self):
        self.type_text("Hi-😀")
        self.assertEqual(self.client.marked, "Hi—😀")
        self.assertEqual(self.client.selection, (5, 0))
        self.assertTrue(self.key(48, "\t"))
        self.assertFalse(self.client.commits)
        self.key(51)
        self.assertEqual(self.client.marked, "Hi—")
        self.key(36)
        self.assertEqual(self.client.commits, ["Hi—"])

    def test_rewrite_converts_in_place_without_a_list(self):
        self.type_text("draft")
        state = self.controller.state
        old_revision = state.revision
        self.type_text("!")
        self.controller.worker.result = (old_revision, {"text": "stale"})
        self.controller.pollSuggestions_(None)
        self.assertEqual(state.candidate, "")
        self.controller.worker.result = (state.revision, {"text": "A considered draft."})
        self.controller.pollSuggestions_(None)
        self.assertFalse(self.controller.panel.visible)  # rewrite has no list
        self.assertEqual(self.client.marked, "draft!")
        self.key(48)  # Tab converts: the rewrite in place of your words
        self.assertEqual((self.client.marked, self.client.commits), ("A considered draft.", []))
        self.key(53)  # Esc: your words again
        self.assertEqual(self.client.marked, "draft!")
        self.key(48)
        self.key(48)  # Tab again keeps it
        self.assertEqual(self.client.commits, ["A considered draft."])

    def test_esc_in_instruct_goes_back_a_step_then_drops(self):
        self.key(98)
        self.key(98)  # instruct
        self.type_text("say hi")
        state, worker = self.controller.state, self.controller.worker
        self.key(36)  # send
        worker.result = (state.revision, {"text": "Hello.", "candidates": ["Hello.", "Hi there."]})
        self.controller.pollSuggestions_(None)
        self.assertTrue(self.controller.panel.visible)
        self.assertTrue(self.key(53))  # Esc: the drafts close, the instruction stays to refine
        self.assertEqual((state.text, state.candidates, self.controller.panel.visible), ("say hi", [], False))
        self.assertEqual(self.client.marked, "say hi")
        self.type_text(", warmly")  # refine and send again: a follow-up in the same conversation
        self.key(36)
        self.assertTrue(state.working and worker.immediate)
        self.assertTrue(self.key(53))  # Esc while it works: back to the instruction
        self.assertFalse(state.working)
        self.assertTrue(self.key(53))  # Esc again: the instruction is dropped, nothing inserted
        self.assertEqual((state.text, self.client.marked, self.client.commits), ("", "", []))

    def test_shortcuts_and_navigation_commit_original_and_pass_through(self):
        self.type_text("original")
        self.assertFalse(self.key(8, "c", self.module.NSEventModifierFlagCommand))
        self.assertEqual(self.client.commits, ["original"])
        self.type_text("next")
        self.assertFalse(self.key(123, "\uf702"))
        self.assertEqual(self.client.commits[-1], "next")

    def test_option_characters_stay_in_composition(self):
        option = 1 << 19  # NSEventModifierFlagOption
        self.type_text("Hi")
        self.assertTrue(self.key(27, "—", option))  # Option+Shift+- on a US layout
        self.assertTrue(self.key(5, "€", option))
        self.assertEqual(self.client.marked, "Hi—€")
        self.assertFalse(self.client.commits)
        self.assertFalse(self.key(123, "", option))  # Option+Left still navigates
        self.assertEqual(self.client.commits, ["Hi—€"])

    def test_f7_switches_mode_and_drops_the_old_candidate(self):
        self.type_text("thank the team")
        state = self.controller.state
        state.offer(state.revision, "A rewrite.")
        self.assertTrue(self.key(98))
        # Continue types into the app: the held words go in, and stay as the model's context.
        self.assertEqual((state.mode, state.candidate, state.text), ("continue", "", "thank the team"))
        self.assertEqual(self.client.commits, ["thank the team"])
        self.assertNotEqual(self.controller.worker.modes[-1], "continue")  # mid-word: no suggestion yet
        self.key(49, " ")
        self.assertEqual(self.controller.worker.modes[-1], "continue")  # a word boundary asks
        self.key(98)
        self.assertEqual((state.mode, state.text), ("instruct", ""))  # the words are in the app already
        self.type_text("say thanks")
        self.key(36)
        self.controller.worker.result = (state.revision, {"text": "Thank you, team—truly."})
        self.controller.pollSuggestions_(None)
        self.key(48)
        self.assertEqual(self.client.commits, ["thank the team", " ", "Thank you, team—truly."])
        self.assertTrue(self.key(98))  # F7 is the input method's while it is active
        self.assertEqual(state.mode, "rewrite")

    def test_instruct_lists_several_readings_and_digits_pick(self):
        self.key(98)
        self.key(98)  # instruct
        self.key(0, "x")
        state, worker = self.controller.state, self.controller.worker
        self.assertTrue(self.key(36))
        worker.result = (state.revision, {"text": "Hello.", "candidates": ["Hello.", "Hi there."]})
        self.controller.pollSuggestions_(None)
        self.assertEqual(self.controller.candidates_(None), ["Hello.", "Hi there."])
        self.assertTrue(self.key(19, "2"))
        self.assertEqual(self.client.commits, ["Hi there."])
        self.assertEqual(state.text, "")

    def test_an_agents_question_is_answered_with_a_digit(self):
        self.key(98)
        self.key(98)  # instruct
        self.key(0, "x")
        state, worker = self.controller.state, self.controller.worker
        self.assertTrue(self.key(36))  # send: the agent starts working
        question = {"id": "perm-1", "text": "Allow Bash?", "choices": [
            {"label": "Allow", "legend": "Bash: git status"}, {"label": "Deny"}]}
        worker.result = (state.revision, {"question": question, "session": "s1"})
        self.controller.pollSuggestions_(None)
        self.assertEqual(self.controller.candidates_(None), ["Allow — Bash: git status", "Deny"])
        self.assertTrue(self.key(19, "2"))
        self.assertEqual(worker.answered, ("s1", "perm-1", 1))
        self.assertIsNone(state.question)
        self.assertEqual(self.client.commits, [])  # an answer is not text

    def test_instruct_waits_for_enter_then_inserts_the_result(self):
        self.key(98)
        self.key(98)  # instruct
        self.key(0, "x")
        state, worker = self.controller.state, self.controller.worker
        sent = len(worker.modes)
        self.type_text("rite a story")
        self.assertEqual(len(worker.modes), sent)  # no requests while typing an instruction
        self.assertTrue(self.key(100))  # F8: send a picture of the window too
        self.assertTrue(state.look)
        self.assertTrue(self.key(36))  # Enter sends
        self.assertTrue(state.working and worker.immediate and worker.look)
        self.assertTrue(self.key(36))  # still working: Enter waits
        self.assertEqual(self.client.commits, [])
        worker.result = (state.revision, {"error": "agent failed"})
        self.controller.pollSuggestions_(None)
        self.assertTrue(state.failed and not state.working)
        self.key(36)  # retry
        worker.result = (state.revision, {"text": "Once upon a time—a cat."})
        self.controller.pollSuggestions_(None)
        self.key(36)  # the second Enter inserts the result
        self.assertEqual(self.client.commits, ["Once upon a time—a cat."])

    def test_requests_name_the_focused_app(self):
        self.type_text("hi")
        self.assertEqual(self.controller.worker.app, "com.apple.TextEdit")

    def test_deactivation_commits_and_closes_worker_timer(self):
        self.type_text("keep me")
        worker, timer = self.controller.worker, self.controller.timer
        self.controller.deactivateServer_(None)
        self.assertEqual(self.client.commits, ["keep me"])
        self.assertTrue(worker.closed)
        self.assertTrue(timer.invalidated)
        self.assertFalse(self.key(0, "x"))
        self.controller.activateServer_(None)
        self.assertTrue(self.key(0, "y"))

    def test_host_commit_and_mouse_candidate_selection(self):
        self.type_text("plain")
        self.controller.commitComposition_(None)
        self.assertEqual(self.client.commits[-1], "plain")
        self.type_text("more")
        self.controller.state.offer(self.controller.state.revision, "More, thoughtfully.")
        self.controller.candidateSelected_("stale candidate")
        self.assertEqual(len(self.client.commits), 1)
        self.controller.candidateSelected_("More, thoughtfully.")
        self.assertEqual(self.client.commits[-1], "More, thoughtfully.")

    def test_continue_starts_from_the_text_box_and_the_suggestion_is_grey(self):
        client = TextClient("Thanks for the review ")
        fresh = self.module.ClaudishInputController().initWithServer_delegate_client_(object(), None, client)
        fresh.activateServer_(None)
        try:
            event = types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 0, modifierFlags=lambda: 0,
                                          characters=lambda: "o")
            fresh.handleEvent_client_(event, client)
            self.assertEqual(fresh.state.text, "Thanks for the review o")  # the app's text, then the key
            fresh.state.change("Thanks for the review ")
            fresh.state.offer(fresh.state.revision, "Thanks for the review on the parser.")
            fresh.changed(client)
            self.assertEqual((client.marked.text, client.marked.attributes),
                             ("on the parser.", {"NSColor": "secondaryLabelColor"}))
        finally:
            fresh.inputControllerWillClose()

    def test_an_instruction_takes_the_text_box_but_not_itself(self):
        client = TextClient("Dear Ana,\n\n")
        fresh = self.module.ClaudishInputController().initWithServer_delegate_client_(object(), None, client)
        fresh.activateServer_(None)
        try:
            fresh.state.mode = "instruct"
            for char in "say hi":
                fresh.handleEvent_client_(types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 0,
                                          modifierFlags=lambda: 0, characters=lambda c=char: c), client)
            self.assertEqual(client.whole(), "Dear Ana,\n\nsay hi")  # the instruction is marked text
            fresh.handleEvent_client_(types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 36,
                                      modifierFlags=lambda: 0, characters=lambda: "\r"), client)
            self.assertEqual(fresh.worker.sent, ("say hi", "Dear Ana,\n\n", ""))
        finally:
            fresh.inputControllerWillClose()

    def test_a_client_without_text_access_gives_no_context(self):
        self.assertEqual(self.controller.around_caret(self.client), ("", ""))  # Client lacks selectedRange

    def test_bundle_registration_names_match_controller(self):
        with (ROOT / "platforms/macos/Info.plist").open("rb") as source:
            info = plistlib.load(source)
        self.assertEqual(info["InputMethodServerControllerClass"], self.module.ClaudishInputController.__name__)
        self.assertEqual(info["InputMethodConnectionName"], "Claudish_Connection")
        self.assertEqual(info["TISIntendedLanguage"], "en")


if __name__ == "__main__":
    unittest.main()
