#!/usr/bin/python3
"""IBus adapter. Run using the system Python that supplies python3-gi."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import gi
gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus
from claudish.composition import LABELS, Composition
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
        self.app = None  # The focused program, for bindings ("supported text boxes").
        self.timer = GLib.timeout_add(40, self.poll)

    def poll(self):
        result = self.suggestions.poll()
        if result:
            revision, data = result
            if "text" in data and self.composition.offer(revision, data["text"], data.get("candidates", ())):
                self.render()
            elif "question" in data and self.composition.ask(revision, data["question"], data["session"]):
                self.render()
            elif ("progress" in data or "partial" in data) and \
                    self.composition.note(revision, data.get("progress") or data.get("partial")):
                self.render()
            elif "error" in data:
                self.composition.fail(revision)
                self.render()
        return True

    def render(self):
        text = self.composition.text
        self.update_preedit_text_with_mode(IBus.Text.new_from_string(text), len(text), bool(text),
                                          IBus.PreeditFocusMode.COMMIT)
        state = self.composition
        # Several readings of an instruction: a numbered list, like any CJK input method's.
        if state.choosing:
            table = IBus.LookupTable.new(9, 0, True, False)
            lines = ([c.get("label", "") + (" — " + c["legend"] if c.get("legend") else "")
                      for c in state.question["choices"]] if state.question else state.candidates)
            for line in lines:
                table.append_candidate(IBus.Text.new_from_string(line))
            self.update_lookup_table(table, True)
        else:
            self.hide_lookup_table()
        if state.question:
            hint = "agent asks: %s · 1–%d: choose · Esc: stop" % (state.question.get("text", ""),
                                                                  len(state.question["choices"]))
        elif state.working and state.status:
            hint = "instruct · %s · Esc: stop" % " ".join(state.status.split())[-90:]
        elif state.choosing:
            hint = "instruct · 1–%d: insert that one · Enter: the first · Esc: keep your words" % len(state.candidates)
        elif state.candidate:
            hint = LABELS[state.mode] + state.candidate
        elif state.working:
            hint = "instruct · %s… · Esc: keep your words" % ("looking and working" if state.look else "working")
        elif state.failed:
            hint = "instruct · the request failed · Enter: retry · Esc: keep your words"
        elif state.mode == "instruct":
            hint = ("instruct + window picture · Enter: send · F8: no picture" if state.look else
                    "instruct · Enter: send · F8: look at the window · F7: mode · Esc: keep your words")
        else:
            hint = "%s · F7: mode · Enter/Esc: keep wording" % state.mode
        self.update_auxiliary_text(IBus.Text.new_from_string(hint), bool(text))

    def changed(self):
        if self.composition.automatic or not self.composition.text:
            self.suggestions.schedule(self.composition.revision, self.composition.text, self.composition.mode,
                                      app=self.app)
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
        if keyval == IBus.KEY_F8 and self.composition.toggle_look():
            self.render()
            return True
        if keyval == IBus.KEY_F7 and self.composition.text:
            self.composition.next_mode()
            self.changed()
            return True
        if self.composition.question and IBus.KEY_1 <= keyval <= IBus.KEY_9:
            chosen = self.composition.answer_choice(keyval - IBus.KEY_0)
            if chosen:
                self.suggestions.answer(*chosen)
                self.render()
            return True
        if self.composition.choosing and IBus.KEY_1 <= keyval <= IBus.KEY_9:
            text = self.composition.pick(keyval - IBus.KEY_0)
            if text is None:
                return True  # no such candidate: ignore the key rather than type it
            self.changed()
            self.commit_text(IBus.Text.new_from_string(text))
            return True
        if keyval in (IBus.KEY_Return, IBus.KEY_KP_Enter):
            action = self.composition.enter()
            if action == "submit":  # Instruct: Enter sends the held text now.
                self.composition.submit()
                self.suggestions.schedule(self.composition.revision, self.composition.text,
                                          self.composition.mode, immediate=True, app=self.app,
                                          look=self.composition.look)
                self.render()
            elif action in ("accept", "keep"):
                self.finish(action == "accept")
            return action != "pass"
        if keyval in (IBus.KEY_Escape, IBus.KEY_Tab):
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

    def do_focus_in_id(self, object_path, client):
        # IBus 1.5.27+: client is "<im module>:<program>", for example "gtk3-im:firefox".
        self.app = None if client in ("", "fake") else client.split(":", 1)[-1]

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
    engines = iter(range(1, 1 << 30))

    def create(factory, name):
        # has_focus_id makes IBus report which program has focus (do_focus_in_id).
        return ClaudishEngine(engine_name=name, connection=bus.get_connection(), has_focus_id=True,
                              object_path="/org/freedesktop/IBus/Engine/Claudish/%d" % next(engines))

    factory.connect("create-engine", create)
    bus.request_name("org.freedesktop.IBus.Claudish", 0)
    bus.connect("disconnected", lambda *_: IBus.quit())
    IBus.main()


if __name__ == "__main__":
    main()
