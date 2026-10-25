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
        self.marked = getattr(text, "text", text)  # the words of an attributed string
        self.attributes = getattr(text, "attributes", None)
        self.selection = selection

    def insertText_replacementRange_(self, text, replacement):
        self.commits.append(text)
        self.marked = ""

    def bundleIdentifier(self):
        return "com.apple.TextEdit"



class TextClient(Client):
    """A client that shares its text, like NSTextView: the app's text with the marked text at the
    caret (mark_at), which a replacement range can move into the middle of it."""

    def __init__(self, text):
        super().__init__()
        self.text, self.mark_at, self.chosen = text, len(text), None

    def marked_text(self):
        return getattr(self.marked, "text", self.marked)

    def insertText_replacementRange_(self, text, replacement):
        super().insertText_replacementRange_(text, replacement)
        self.text = self.text[:self.mark_at] + text + self.text[self.mark_at:]
        self.mark_at += len(text)

    def setMarkedText_selectionRange_replacementRange_(self, text, selection, replacement):
        if replacement[0] == 2**63 - 1 and self.chosen and not self.marked_text():
            replacement = self.chosen  # with nothing marked, marked text replaces the selection (AppKit)
        if replacement[0] != 2**63 - 1:  # replaces part of the app's text (the selection)
            start, length = replacement
            self.text, self.mark_at, self.chosen = self.text[:start] + self.text[start + length:], start, None
        super().setMarkedText_selectionRange_replacementRange_(text, selection, replacement)

    def whole(self):
        return self.text[:self.mark_at] + self.marked_text() + self.text[self.mark_at:]

    def length(self):
        return len(self.whole())

    def selectedRange(self):
        if self.chosen:  # a selection in the app's own text
            return self.chosen
        return (self.mark_at + (self.selection or (len(self.marked_text()), 0))[0], 0)

    def markedRange(self):
        marked = self.marked_text()
        return (self.mark_at, len(marked)) if marked else (2**63 - 1, 0)

    def attributedSubstringFromRange_(self, span):
        return types.SimpleNamespace(string=lambda: self.whole()[span[0]:span[0] + span[1]])

    def stringFromRange_actualRange_(self, span, actual):
        raise AssertionError("crashes in IMK when PyObjC passes a NULL actualRange")

    def attributesForCharacterIndex_lineHeightRectangle_(self, index, rect):
        # IMK indexes the inline session; without one, zero asks for the selection.
        base = self.mark_at if self.marked_text() else self.selectedRange()[0]
        return {}, ((10 * (base + index), 400), (1, 18))


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
    """cd_AI's panel (platforms/macos/panel.py): records what it shows."""

    def __init__(self, toast=False):
        self.visible, self.spec, self.pick, self.rect = False, None, None, None

    def show(self, rect, spec, pick=None):
        self.visible, self.spec, self.pick, self.rect = True, spec, pick, rect

    def hide(self):
        self.visible, self.spec = False, None

    @property
    def rows(self):
        return [row["text"] for row in self.spec["rows"]] if self.spec else []


class Overlay:
    """The suggestion overlay: records the text it draws after the caret."""

    def __init__(self):
        self.text = ""

    def show(self, rect, text):
        self.text = text

    def hide(self):
        self.text = ""

    def visible(self):
        return bool(self.text)


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
        self.offline = False
        self.summon = "Shift+Enter"
        self.modes = []

    def answer(self, session, question, choice=None, text=None):
        self.answered = (session, question, choice)
        self.answered_text = (session, question, text)

    def schedule(self, revision, text, mode="rewrite", immediate=False, app=None, look=False, before="", after="",
                 purpose=None):
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
    objc.registerMetaDataForSelector = lambda *args: None
    objc._C_OUT = b"o"
    appkit = types.ModuleType("AppKit")
    appkit.NSAttributedString = Grey
    appkit.NSColor = types.SimpleNamespace(secondaryLabelColor=lambda: "secondaryLabelColor", textColor=lambda: "textColor")
    appkit.NSForegroundColorAttributeName = "NSColor"
    appkit.NSEvent = types.SimpleNamespace(mouseLocation=lambda: types.SimpleNamespace(x=500, y=300))
    for name, value in {"NSEventMaskKeyDown": 1024, "NSEventTypeKeyDown": 10,
                        "NSEventMaskFlagsChanged": 4096, "NSEventTypeFlagsChanged": 12,
                        "NSEventModifierFlagShift": 1 << 17,
                        "NSEventModifierFlagCommand": 1 << 20,
                        "NSEventModifierFlagControl": 1 << 18,
                        "NSEventModifierFlagOption": 1 << 19}.items():
        setattr(appkit, name, value)
    foundation = types.ModuleType("Foundation")
    foundation.NSNotFound = 2**63 - 1
    foundation.NSTimer = Timer
    imk = types.ModuleType("InputMethodKit")
    imk.IMKInputController = BaseController
    imk.kIMKLocateCandidatesBelowHint = 2
    panel = types.ModuleType("panel")
    panel.Panel, panel.Overlay = Panel, Overlay
    spec = importlib.util.spec_from_file_location("claudish_macos_test", ROOT / "platforms/macos/controller.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", {"objc": objc, "AppKit": appkit, "panel": panel,
                                     "Foundation": foundation, "InputMethodKit": imk}):
        spec.loader.exec_module(module)
    module.Suggestions = Worker
    return module


class MacOSAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_adapter()
        # These tests press Enter the moment a result arrives; the double-Enter guard is tested in
        # test_candidates.
        # (through the adapter's own module: loading it under patched sys.modules can leave a copy)
        cls.guard = patch.dict(cls.module.Composition.enter.__globals__, {"ROLLED_SHIFT_SECONDS": 0})
        cls.guard.start()

    @classmethod
    def tearDownClass(cls):
        cls.guard.stop()

    def setUp(self):
        self.client = Client()
        self.controller = self.module.ClaudishInputController().initWithServer_delegate_client_(
            object(), None, self.client)
        self.controller.activateServer_(None)
        self.assertEqual(self.controller.state.mode, "compose")  # a new session starts in compose

    def tearDown(self):
        self.controller.inputControllerWillClose()

    def test_continue_types_like_en_us(self):
        fresh = self.module.ClaudishInputController().initWithServer_delegate_client_(object(), None, self.client)
        fresh.activateServer_(None)
        try:
            fresh.state.mode = "continue"
            for char in "ls -la":
                self.assertTrue(fresh.handleEvent_client_(types.SimpleNamespace(
                    type=lambda: 10, keyCode=lambda: 0, modifierFlags=lambda: 0, characters=lambda c=char: c), self.client))
            self.assertEqual("".join(self.client.commits), "ls -la")  # straight in; the hyphen stays a hyphen
            self.assertFalse(fresh.handleEvent_client_(types.SimpleNamespace(  # Tab with nothing offered is the app's
                type=lambda: 10, keyCode=lambda: 48, modifierFlags=lambda: 0, characters=lambda: "\t"), self.client))
        finally:
            fresh.inputControllerWillClose()

    def shift_tap(self):
        """Shift pressed and released alone: flagsChanged events, as macOS sends them."""
        for flags in (1 << 17, 0):
            event = types.SimpleNamespace(type=lambda: 12, keyCode=lambda: 56, modifierFlags=lambda f=flags: f,
                                          characters=lambda: "")
            self.assertFalse(self.controller.handleEvent_client_(event, self.client))  # the app sees it too

    def key(self, code, text="", flags=0):
        event = types.SimpleNamespace(type=lambda: 10, keyCode=lambda: code,
                                      modifierFlags=lambda: flags, characters=lambda: text)
        return self.controller.handleEvent_client_(event, self.client)

    def type_text(self, text):
        for char in text:
            self.assertTrue(self.key(0, char))

    def test_typed_text_utf16_ranges_and_pending_tab(self):
        self.type_text("Hi-😀")
        self.assertEqual(self.client.marked, "Hi-😀")
        self.assertEqual(self.client.selection, (5, 0))
        self.assertTrue(self.key(48, "\t"))
        self.assertFalse(self.client.commits)
        self.key(51)
        self.assertEqual(self.client.marked, "Hi-")
        self.assertFalse(self.key(36, "\r"))  # Enter keeps your words as they are, and the app gets its Enter
        self.assertEqual(self.client.commits, ["Hi-"])
        self.assertEqual(self.controller.state.mode, "compose")

    def test_enter_keeps_and_reaches_the_app_and_shift_enter_asks(self):
        self.type_text("on my way")
        self.assertFalse(self.key(36, "\r"))  # the app gets its Enter: a chat box sends
        self.assertEqual(self.client.commits, ["on my way"])
        self.type_text("say thanks")
        self.assertTrue(self.key(36, "\r", 1 << 17))  # Shift+Enter asks the model
        self.assertEqual(self.controller.worker.modes[-1], "instruct")

    def test_enter_keeps_without_leaving_empty_marked_text(self):
        # Terminal beeps at a Return that arrives with (empty) marked text still open.
        calls = []
        client = self.client
        client.markedRange = lambda: (0, len(client.marked))
        mark, insert = client.setMarkedText_selectionRange_replacementRange_, client.insertText_replacementRange_
        client.setMarkedText_selectionRange_replacementRange_ = lambda text, *rest: (
            calls.append(("mark", getattr(text, "text", text))), mark(text, *rest))
        client.insertText_replacementRange_ = lambda text, *rest: (calls.append(("insert", text)), insert(text, *rest))
        self.type_text("ls")
        del calls[:]
        self.assertFalse(self.key(36, "\r"))
        self.assertEqual(calls, [("insert", "ls")])

    def test_rewrite_converts_in_place_without_a_list(self):
        self.type_text("draft")
        state = self.controller.state
        old_revision = state.revision
        self.type_text("!")
        self.controller.worker.result = (old_revision, {"text": "stale"})
        self.controller.pollSuggestions_(None)
        self.assertEqual(state.candidate, "")
        self.assertEqual(self.controller.worker.modes, [])  # nothing is asked while you type
        self.key(48)  # Tab asks
        self.assertEqual((self.controller.worker.modes[-1], self.controller.worker.immediate), ("rewrite", True))
        self.controller.worker.result = (state.revision, {"text": "A considered draft."})
        self.controller.pollSuggestions_(None)  # it arrives: in place of your words, no list
        # In place of your words; the panel keeps yours, as large, until you keep it.
        # Your words stay the marked text; the rewrite waits in the panel for Tab (a click or a focus
        # change, which apps turn into a commit, can never insert the model's words).
        self.assertEqual((self.module.PANEL.rows, self.module.PANEL.spec["label"], self.module.PANEL.spec["body"]),
                         ([], "Rewrite", "A considered draft."))
        self.assertEqual(self.module.PANEL.spec["foot"], [("Tab", "insert"), ("Esc", "dismiss")])
        self.assertEqual((self.client.marked, self.client.commits), ("draft!", []))
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
        self.key(36, "\r", 1 << 17)  # send
        worker.result = (state.revision, {"text": "Hello.", "candidates": ["Hello.", "Hi there."]})
        self.controller.pollSuggestions_(None)
        self.assertEqual(self.module.PANEL.rows, ["Hello.", "Hi there."])
        self.assertTrue(self.key(53))  # Esc: the drafts close, the instruction stays to refine
        self.assertEqual((state.text, state.candidates, self.module.PANEL.rows), ("say hi", [], []))
        self.assertEqual(self.client.marked, "say hi")
        self.type_text(", warmly")  # refine and send again: a follow-up in the same conversation
        self.key(36, "\r", 1 << 17)
        self.assertTrue(state.working and worker.immediate)
        self.assertTrue(self.key(53))  # Esc while it works: back to the instruction
        self.assertFalse(state.working)
        self.assertTrue(self.key(53))  # Esc again: the instruction is dropped, nothing inserted
        self.assertEqual((state.text, self.client.marked, self.client.commits), ("", "", []))

    def test_a_leading_space_goes_to_the_app(self):
        self.assertTrue(self.key(49, " "))
        self.assertEqual((self.client.commits, self.controller.state.text), ([" "], ""))
        self.type_text("hi there")
        self.assertEqual(self.client.marked, "hi there")

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

    def test_ctrl_shift_is_a_chord_not_a_tap(self):
        self.controller.shift.typed_at = 0  # long after any key: only the chord decides
        for flags in ((1 << 17) | (1 << 18), 1 << 18):  # Shift down, then up, with Control held
            event = types.SimpleNamespace(type=lambda: 12, keyCode=lambda: 56, modifierFlags=lambda f=flags: f,
                                          characters=lambda: "")
            self.controller.handleEvent_client_(event, self.client)
        self.assertEqual(self.controller.state.mode, "compose")

    def test_a_shift_tap_switches_mode_and_keeps_what_you_typed(self):
        self.type_text("thank the team")
        state = self.controller.state
        self.shift_tap()
        # Continue types into the app: your words go in as typed, and stay as the model's context.
        self.assertEqual((state.mode, state.text), ("continue", "thank the team"))
        self.assertEqual(self.client.commits, ["thank the team"])
        self.assertNotIn("continue", self.controller.worker.modes)  # mid-word: no suggestion yet
        self.key(49, " ")
        self.assertEqual(self.controller.worker.modes[-1], "continue")  # a word boundary asks
        self.shift_tap()
        self.assertEqual((state.mode, state.text), ("compose", ""))  # the words are in the app already
        self.type_text("say thanks")
        self.key(36, "\r", 1 << 17)  # Shift+Enter: an instruction
        self.assertEqual(self.controller.worker.modes[-1], "instruct")
        self.controller.worker.result = (state.revision, {"text": "Thank you, team—truly."})
        self.controller.pollSuggestions_(None)
        self.key(48)
        self.assertEqual(self.client.commits, ["thank the team", " ", "Thank you, team—truly."])
        # Shift held for a capital is not a tap.
        for flags in (1 << 17,):
            self.controller.handleEvent_client_(types.SimpleNamespace(type=lambda: 12, keyCode=lambda: 56,
                                                modifierFlags=lambda: flags, characters=lambda: ""), self.client)
        self.key(0, "A", 1 << 17)
        self.controller.handleEvent_client_(types.SimpleNamespace(type=lambda: 12, keyCode=lambda: 56,
                                            modifierFlags=lambda: 0, characters=lambda: ""), self.client)
        self.assertEqual(state.mode, "compose")

    def test_instruct_lists_several_drafts_and_arrow_tab_takes_one(self):
        self.key(0, "x")
        state, worker = self.controller.state, self.controller.worker
        self.assertTrue(self.key(36, "\r", 1 << 17))
        self.assertEqual(getattr(self.client.marked, "text", self.client.marked), "x")  # it stays marked: the keys keep coming
        self.assertEqual(self.client.attributes, {"NSUnderline": 1, "NSUnderlineColor": "textColor"})  # one plain underline
        worker.result = (state.revision, {"text": "Hello.", "candidates": ["Hello.", "Hi there."]})
        self.controller.pollSuggestions_(None)
        self.assertEqual(self.module.PANEL.rows, ["Hello.", "Hi there."])
        self.assertTrue(self.key(125))  # ↓ highlights the second
        self.assertTrue(self.key(48))  # and Tab inserts it (Enter never inserts the model's text)
        self.assertEqual(self.client.commits, ["Hi there."])
        self.assertEqual(state.text, "")

    def test_an_approval_is_answered_with_the_arrows(self):
        self.key(0, "x")
        state, worker = self.controller.state, self.controller.worker
        self.assertTrue(self.key(36, "\r", 1 << 17))  # send: the agent starts working
        question = {"id": "perm-1", "text": "Allow Bash?", "permission": True, "label": "Claude Code wants to run",
                    "body": "git status", "code": True, "choices": [{"label": "Deny"}, {"label": "Allow"}]}
        worker.result = (state.revision, {"question": question, "session": "s1"})
        self.controller.pollSuggestions_(None)
        spec = self.module.PANEL.spec  # what is approved in full; nothing highlighted
        self.assertEqual((spec["label"], spec["body"], self.module.PANEL.rows, spec["on"]),
                         ("Claude Code wants to run", "git status", ["Deny", "Allow"], -1))
        self.assertTrue(self.key(125) and self.key(125))  # ↓ Deny, ↓ Allow
        self.assertTrue(self.key(48, "\t"))  # and Tab confirms it
        self.assertEqual(worker.answered, ("s1", "perm-1", 1))
        self.assertIsNone(state.question)
        self.assertEqual(self.client.commits, [])  # an answer is not text
        worker.result = (state.revision, {"question": dict(question, id="perm-2"), "session": "s1"})
        self.controller.pollSuggestions_(None)
        self.type_text("not 2")  # words instead of a choice, digits included: a reply
        self.assertEqual(self.client.marked, "not 2")
        self.assertTrue(self.key(36, "\r", 1 << 17))
        self.assertEqual(worker.answered_text, ("s1", "perm-2", "not 2"))

    def test_instruct_waits_for_enter_then_inserts_the_result(self):
        self.key(0, "x")
        state, worker = self.controller.state, self.controller.worker
        sent = len(worker.modes)
        self.type_text("rite a story")
        self.assertEqual(len(worker.modes), sent)  # no requests while typing an instruction
        self.assertTrue(self.key(100))  # F8: send a picture of the window too
        self.assertTrue(state.look)
        self.assertTrue(self.key(36, "\r", 1 << 17))  # Shift+Enter sends
        self.assertTrue(state.working and worker.immediate and worker.look)
        self.assertTrue(self.key(36))  # still working: Enter puts nothing in
        self.assertEqual(self.client.commits, [])
        worker.result = (state.revision, {"error": "agent failed"})
        self.controller.pollSuggestions_(None)
        self.assertTrue(state.failed and not state.working)
        self.key(36, "\r", 1 << 17)  # retry
        worker.result = (state.revision, {"text": "Once upon a time—a cat."})
        self.controller.pollSuggestions_(None)
        self.key(36)  # a reflexive Enter on the draft inserts nothing
        self.assertEqual(self.client.commits, [])
        self.key(48)  # Tab takes the result
        self.assertEqual(self.client.commits, ["Once upon a time—a cat."])

    def test_requests_name_the_focused_app(self):
        self.type_text("hi")
        self.key(48)  # rewrite asks on Tab
        self.assertEqual(self.controller.worker.app, "com.apple.TextEdit")

    def test_deactivation_commits_stops_the_timer_and_keeps_the_worker(self):
        self.type_text("keep me")
        worker, timer = self.controller.worker, self.controller.timer
        self.controller.deactivateServer_(None)
        self.assertEqual(self.client.commits, ["keep me"])
        self.assertFalse(worker.closed)  # a held exchange's answer arrives while you are away
        self.assertTrue(timer.invalidated)
        self.assertFalse(self.key(0, "x"))
        self.controller.activateServer_(None)
        self.assertIs(self.controller.worker, worker)
        self.assertTrue(self.key(0, "y"))

    def test_host_commit_and_a_click_on_a_row(self):
        self.type_text("plain")
        self.controller.commitComposition_(None)
        self.assertEqual(self.client.commits[-1], "plain")
        self.key(0, "x")  # compose (see setUp), then an instruction with two readings
        state, worker = self.controller.state, self.controller.worker
        self.key(36, "\r", 1 << 17)
        worker.result = (state.revision, {"text": "Hello.", "candidates": ["Hello.", "Hi there."]})
        self.controller.pollSuggestions_(None)
        self.module.PANEL.pick(2)  # a click on the second row
        self.assertEqual(self.client.commits[-1], "Hi there.")

    def test_the_input_menu_switches_modes_as_a_shift_tap_does(self):
        self.assertEqual(self.controller.state.mode, "compose")
        self.controller.chooseContinue_(None)
        self.assertEqual(self.controller.state.mode, "continue")
        self.controller.chooseContinue_(None)  # already there: nothing changes
        self.assertEqual(self.controller.state.mode, "continue")
        self.controller.chooseCompose_(None)
        self.assertEqual(self.controller.state.mode, "compose")

    def test_the_input_menu_is_kept_and_its_tick_follows_the_mode(self):
        class Item:
            def __init__(self, title=""): self.name, self.ticked = title, 0
            @classmethod
            def alloc(cls): return cls()
            def initWithTitle_action_keyEquivalent_(self, title, action, key): self.name = title; return self
            @classmethod
            def separatorItem(cls): return cls()
            def setTarget_(self, target): pass
            def setState_(self, state): self.ticked = state
            def title(self): return self.name

        class Menu:
            @classmethod
            def alloc(cls): return cls()
            def initWithTitle_(self, title): self.items = []; return self
            def addItem_(self, item): self.items.append(item)
            def itemArray(self): return self.items

        appkit = types.ModuleType("AppKit")
        appkit.NSMenu, appkit.NSMenuItem = Menu, Item
        with patch.dict("sys.modules", {"AppKit": appkit}):
            menu = self.controller.menu()
            self.assertEqual([(item.name, item.ticked) for item in menu.items][:2], [("Compose", 1), ("Continue", 0)])
            self.controller.chooseContinue_(None)
            self.assertIs(self.controller.menu(), menu)  # macOS asks after nearly every key: one menu
            self.assertEqual([item.ticked for item in menu.items][:2], [0, 1])

    def test_a_password_field_gets_its_keys_untouched(self):
        with patch.object(self.module, "secure_input", return_value=True):
            for char in "hunter2":
                self.assertFalse(self.key(0, char))  # straight in: the app types it
            self.assertFalse(self.key(53, "\x1b"))
        self.assertEqual((self.controller.state.text, self.client.marked, self.module.PANEL.visible), ("", "", False))

    def test_a_shortcut_in_continue_leaves_a_selected_word_alone(self):
        client = TextClient("keep this word")
        client.chosen = (5, 4)  # "this", selected in the app
        fresh = self.module.ClaudishInputController().initWithServer_delegate_client_(object(), None, client)
        fresh.activateServer_(None)
        try:
            fresh.state.mode = "continue"
            fresh.handleEvent_client_(types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 14,
                                                            modifierFlags=lambda: 1 << 18, characters=lambda: "e"), client)
            self.assertEqual(client.whole(), "keep this word")
        finally:
            fresh.inputControllerWillClose()

    def test_without_a_caret_the_panel_goes_by_the_pointer_not_a_corner(self):
        client = TextClient("x")
        client.attributesForCharacterIndex_lineHeightRectangle_ = lambda index, rect: ({}, ((0, 0), (1, 18)))
        client.firstRectForCharacterRange_actualRange_ = lambda span, actual: ((0, 0), (0, 0))
        self.assertEqual(self.controller.caret(client), ((500, 282), (0, 18)))

    def test_line_rect_uses_inline_offsets_after_existing_text(self):
        client = TextClient("https://example.test/")
        seen = []
        original = client.attributesForCharacterIndex_lineHeightRectangle_
        def line_rect(index, rect):
            seen.append(index)
            return original(index, rect)
        client.attributesForCharacterIndex_lineHeightRectangle_ = line_rect
        self.controller.caret(client)
        self.assertEqual(seen.pop(), 0)  # no composition: ask for the current selection
        client.setMarkedText_selectionRange_replacementRange_("ok", (2, 0), (self.module.NSNotFound, 0))
        start = self.controller.caret(client, start=True)
        self.assertEqual(seen.pop(), 0)
        end = self.controller.caret(client)
        self.assertEqual(seen.pop(), 2)
        self.assertEqual(end[0][0] - start[0][0], 20)
        # The fallback remains in document coordinates, not the inline offset.
        absolute = []
        client.attributesForCharacterIndex_lineHeightRectangle_ = lambda index, rect: ({}, ((0, 0), (0, 0)))
        def first_rect(span, actual):
            absolute.append(span)
            return ((200, 400), (1, 18)), span
        client.firstRectForCharacterRange_actualRange_ = first_rect
        self.controller.caret(client, start=True)
        self.assertEqual(absolute, [(len("https://example.test/"), 0)])

    def test_shift_esc_brings_a_held_exchange_back_without_asking_again(self):
        """Codex: restoring a running instruction scheduled it a second time (two sessions, the
        second without the text around the caret). Its request is still running."""
        self.type_text("say hi")
        self.key(36, "\r", 1 << 17)  # Shift+Enter: sent
        asked = list(self.controller.worker.modes)
        self.key(0, "a", 1 << 20)  # Cmd+A: a shortcut holds the exchange
        self.assertIsNotNone(self.controller.state.held)
        self.assertTrue(self.key(53, "\x1b", 1 << 17))  # Shift+Esc: back
        self.assertEqual((self.controller.state.text, self.controller.worker.modes), ("say hi", asked))

    def test_the_panel_starts_where_the_composition_starts(self):
        """Under the composition's start, as CJK candidate windows sit, whatever the caret: typed,
        dropped (its toast), or brought back whole by Shift+Esc (docs/design/design.md, Placement)."""
        client = TextClient("Dear Sam, ")
        fresh = self.module.ClaudishInputController().initWithServer_delegate_client_(object(), None, client)
        fresh.activateServer_(None)
        start = ((100, 400), (1, 18))  # "Dear Sam, " is 10 characters
        try:
            for char in "say hi":
                fresh.handleEvent_client_(types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 0, modifierFlags=lambda: 0,
                                                                characters=lambda c=char: c), client)
            self.assertEqual(self.module.PANEL.rect, start)  # not the caret, 6 characters on
            escape = lambda flags=0: fresh.handleEvent_client_(types.SimpleNamespace(
                type=lambda: 10, keyCode=lambda: 53, modifierFlags=lambda: flags, characters=lambda: "\x1b"), client)
            escape()  # dropped: said where the words were
            self.assertEqual((self.module.TOAST.spec["status"], self.module.TOAST.rect), ("dropped", start))
            escape(self.module.NSEventModifierFlagShift)  # back, whole
            self.assertEqual((client.marked_text(), self.module.PANEL.rect), ("say hi", start))
        finally:
            fresh.inputControllerWillClose()

    def test_continue_starts_from_the_text_box_and_the_suggestion_is_grey(self):
        client = TextClient("Thanks for the review ")
        fresh = self.module.ClaudishInputController().initWithServer_delegate_client_(object(), None, client)
        fresh.activateServer_(None)
        try:
            fresh.state.mode = "continue"
            event = types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 0, modifierFlags=lambda: 0,
                                          characters=lambda: "o")
            fresh.handleEvent_client_(event, client)
            self.assertEqual(fresh.state.text, "Thanks for the review o")  # the app's text, then the key
            fresh.state.change("Thanks for the review ")
            fresh.state.offer(fresh.state.revision, "Thanks for the review on the parser.")
            fresh.changed(client)
            # Nothing follows on the line: our overlay draws it grey after the caret, nothing is marked.
            self.assertEqual((self.module.OVERLAY.text, client.marked), ("on the parser.", ""))
            # The caret moves without a key (a click): macOS says nothing, so the suggestion is
            # dropped when the caret is seen elsewhere, and Tab cannot take it unseen.
            fresh.ghost_checked = 0
            fresh.caret = lambda _client: ((500.0, 300.0), (2.0, 17.0))
            fresh.check_ghost()
            self.assertEqual((self.module.OVERLAY.text, fresh.state.ghost), ("", ""))
            del fresh.caret
            fresh.state.offer(fresh.state.revision, "Thanks for the review on the parser.")
            fresh.changed(client)
            # Text after the caret on its line: nothing covers it.
            client.text, client.mark_at = "Thanks for the review  today.", len("Thanks for the review ")
            fresh.changed(client)
            self.assertEqual((self.module.OVERLAY.text, client.marked), ("", ""))
        finally:
            fresh.inputControllerWillClose()

    def test_continue_is_quiet_in_a_terminal(self):
        client = TextClient("~ % ")
        client.bundleIdentifier = lambda: "com.apple.Terminal"
        fresh = self.module.ClaudishInputController().initWithServer_delegate_client_(object(), None, client)
        fresh.activateServer_(None)
        try:
            for char in "ls ":
                fresh.handleEvent_client_(types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 0, modifierFlags=lambda: 0,
                                                                characters=lambda char=char: char), client)
            self.assertTrue(fresh.state.quiet)
            self.assertNotIn("continue", fresh.worker.modes)  # a command line is not prose: nothing unasked
        finally:
            fresh.inputControllerWillClose()

    def test_an_instruction_takes_the_text_box_but_not_itself(self):
        client = TextClient("Dear Ana,\n\n")
        fresh = self.module.ClaudishInputController().initWithServer_delegate_client_(object(), None, client)
        fresh.activateServer_(None)
        try:
            fresh.state.mode = "compose"
            for char in "say hi":
                fresh.handleEvent_client_(types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 0,
                                          modifierFlags=lambda: 0, characters=lambda c=char: c), client)
            self.assertEqual(client.whole(), "Dear Ana,\n\nsay hi")  # the instruction is marked text
            fresh.handleEvent_client_(types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 36,
                                      modifierFlags=lambda: 1 << 17, characters=lambda: "\r"), client)  # Shift+Enter
            self.assertEqual(fresh.worker.sent, ("say hi", "Dear Ana,\n\n", ""))
        finally:
            fresh.inputControllerWillClose()

    def test_a_rewrite_knows_where_it_goes(self):
        client = TextClient("Dear Ana,\n\n")
        fresh = self.module.ClaudishInputController().initWithServer_delegate_client_(object(), None, client)
        fresh.activateServer_(None)
        try:
            fresh.state.mode = "compose"
            for char in "thanks":
                fresh.handleEvent_client_(types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 0,
                                          modifierFlags=lambda: 0, characters=lambda c=char: c), client)
            fresh.handleEvent_client_(types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 48,
                                      modifierFlags=lambda: 0, characters=lambda: "\t"), client)
            self.assertEqual(fresh.worker.sent, ("thanks", "Dear Ana,\n\n", ""))
        finally:
            fresh.inputControllerWillClose()

    def test_tab_in_rewrite_rewrites_a_selection_in_place(self):
        client = TextClient("Dear Ana, this is important. Thanks.")
        client.chosen = (10, 18)  # "this is important."
        fresh = self.module.ClaudishInputController().initWithServer_delegate_client_(object(), None, client)
        fresh.activateServer_(None)
        try:
            fresh.state.mode = "compose"
            tab = types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 48, modifierFlags=lambda: 0, characters=lambda: "\t")
            self.assertTrue(fresh.handleEvent_client_(tab, client))
            self.assertEqual((client.whole(), fresh.worker.sent), ("Dear Ana, this is important. Thanks.",
                             ("this is important.", "Dear Ana, ", " Thanks.")))
            fresh.worker.result = (fresh.state.revision, {"text": "This is of utmost significance."})
            fresh.pollSuggestions_(None)
            # The selection stays as it was (your words, marked); the rewrite waits in the panel for Tab.
            self.assertEqual(client.whole(), "Dear Ana, this is important. Thanks.")
            self.assertEqual(self.module.PANEL.spec["body"], "This is of utmost significance.")
            esc = types.SimpleNamespace(type=lambda: 10, keyCode=lambda: 53, modifierFlags=lambda: 0, characters=lambda: "\x1b")
            fresh.handleEvent_client_(esc, client)
            fresh.handleEvent_client_(esc, client)  # your words, as they were
            self.assertEqual(client.whole(), "Dear Ana, this is important. Thanks.")
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
