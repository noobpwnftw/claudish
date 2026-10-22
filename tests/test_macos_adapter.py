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


class BaseController:
    def initWithServer_delegate_client_(self, server, delegate, client):
        self._client = client
        return self

    def client(self):
        return self._client


class Panel:
    @classmethod
    def alloc(cls):
        return cls()

    def initWithServer_panelType_(self, server, panel_type):
        self.visible = False
        return self

    def updateCandidates(self):
        pass

    def show(self, hint):
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

    def schedule(self, revision, text, mode="rewrite", immediate=False):
        self.result = None
        self.modes.append(mode)
        self.immediate = immediate

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

    def tearDown(self):
        self.controller.inputControllerWillClose()

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

    def test_candidate_panel_accept_and_stale_result(self):
        self.type_text("draft")
        state = self.controller.state
        old_revision = state.revision
        self.type_text("!")
        self.controller.worker.result = (old_revision, {"text": "stale"})
        self.controller.pollSuggestions_(None)
        self.assertFalse(self.controller.panel.visible)
        self.controller.worker.result = (state.revision, {"text": "A considered draft."})
        self.controller.pollSuggestions_(None)
        self.assertEqual(self.controller.candidates_(None), ["A considered draft."])
        self.assertTrue(self.controller.panel.visible)
        self.key(48)
        self.assertEqual(self.client.commits, ["A considered draft."])
        self.assertFalse(self.controller.panel.visible)

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
        self.assertEqual((state.mode, state.candidate), ("continue", ""))
        self.assertEqual(self.controller.worker.modes[-1], "continue")
        self.key(98)
        self.assertEqual(state.mode, "instruct")
        self.controller.worker.result = (state.revision, {"text": "Thank you, team—truly."})
        self.controller.pollSuggestions_(None)
        self.key(48)
        self.assertEqual(self.client.commits, ["Thank you, team—truly."])
        self.assertFalse(self.key(98))  # Without a composition, F7 belongs to the app.

    def test_instruct_waits_for_enter_then_inserts_the_result(self):
        self.key(0, "x")
        self.key(98)
        self.key(98)  # instruct
        state, worker = self.controller.state, self.controller.worker
        sent = len(worker.modes)
        self.type_text("rite a story")
        self.assertEqual(len(worker.modes), sent)  # no requests while typing an instruction
        self.assertTrue(self.key(36))  # Enter sends
        self.assertTrue(state.working and worker.immediate)
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

    def test_bundle_registration_names_match_controller(self):
        with (ROOT / "platforms/macos/Info.plist").open("rb") as source:
            info = plistlib.load(source)
        self.assertEqual(info["InputMethodServerControllerClass"], self.module.ClaudishInputController.__name__)
        self.assertEqual(info["InputMethodConnectionName"], "Claudish_Connection")
        self.assertEqual(info["TISIntendedLanguage"], "en")


if __name__ == "__main__":
    unittest.main()
