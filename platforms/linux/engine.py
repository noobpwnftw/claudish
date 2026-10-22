#!/usr/bin/python3
"""IBus adapter. Run using the system Python that supplies python3-gi."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import gi
gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus
from claudish.composition import Composition
from claudish.client import Suggestions

# Pressed alone, these keys must not end the phrase. AltGr (Level3) types characters.
MODIFIER_KEYS = {getattr(IBus, "KEY_" + name) for name in (
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Super_L", "Super_R",
    "Meta_L", "Meta_R", "Hyper_L", "Hyper_R", "Caps_Lock", "Shift_Lock", "Num_Lock",
    "Scroll_Lock", "ISO_Level3_Shift", "ISO_Level5_Shift", "Mode_switch",
    "ISO_Next_Group", "ISO_Prev_Group")}


class ClaudishEngine(IBus.Engine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.composition = Composition()
        self.suggestions = Suggestions()
        self.sensitive = False
        self.timer = GLib.timeout_add(40, self.poll)

    def poll(self):
        result = self.suggestions.poll()
        if result:
            revision, data = result
            if "text" in data and self.composition.offer(revision, data["text"]):
                self.render()
        return True

    def render(self):
        text = self.composition.text
        self.update_preedit_text_with_mode(IBus.Text.new_from_string(text), len(text), bool(text),
                                          IBus.PreeditFocusMode.COMMIT)
        candidate = self.composition.candidate
        self.update_auxiliary_text(IBus.Text.new_from_string(
            "Tab: " + candidate if candidate else "Typing… · Enter/Esc: keep wording"), bool(text))

    def changed(self):
        self.suggestions.schedule(self.composition.revision, self.composition.text)
        self.render()

    def finish(self, suggested=False):
        text = self.composition.commit(suggested)
        self.changed()
        if text:
            self.commit_text(IBus.Text.new_from_string(text))

    def do_process_key_event(self, keyval, keycode, state):
        if state & IBus.ModifierType.RELEASE_MASK or self.sensitive:
            return False
        if keyval in MODIFIER_KEYS:
            return False
        modifiers = (IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.MOD1_MASK |
                     IBus.ModifierType.SUPER_MASK | IBus.ModifierType.META_MASK)
        if state & modifiers:
            self.finish()
            return False
        self.poll()
        if keyval == IBus.KEY_F6 and self.composition.text:
            self.render()
            return True
        if keyval in (IBus.KEY_Return, IBus.KEY_KP_Enter, IBus.KEY_Escape, IBus.KEY_Tab):
            if not self.composition.text:
                return False
            if keyval == IBus.KEY_Tab and not self.composition.candidate:
                return True
            self.finish(keyval == IBus.KEY_Tab)
            return True
        if keyval == IBus.KEY_BackSpace:
            if not self.composition.text:
                return False
            self.composition.backspace()
            self.changed()
            return True
        char = IBus.keyval_to_unicode(keyval)
        if char and char.isprintable():
            if not self.composition.insert(char):
                self.finish()
                self.composition.insert(char)
            self.changed()
            return True
        self.finish()
        return False

    def do_set_content_type(self, purpose, hints):
        self.sensitive = purpose in (IBus.InputPurpose.PASSWORD, IBus.InputPurpose.PIN)
        if self.sensitive:
            self.do_reset()

    def do_focus_out(self):
        # IBus commits the visible preedit through PreeditFocusMode.COMMIT.
        self.do_reset()

    def do_disable(self):
        self.finish()

    def do_reset(self):
        self.composition.change("")
        self.changed()

    def do_destroy(self):
        GLib.source_remove(self.timer)
        self.suggestions.close()
        IBus.Engine.do_destroy(self)


def main():
    IBus.init()
    bus = IBus.Bus()
    if not bus.is_connected():
        raise SystemExit("IBus daemon is not running in this desktop session")
    factory = IBus.Factory.new(bus.get_connection())
    factory.add_engine("claudish", ClaudishEngine)
    bus.request_name("org.freedesktop.IBus.Claudish", 0)
    bus.connect("disconnected", lambda *_: IBus.quit())
    IBus.main()


if __name__ == "__main__":
    main()
