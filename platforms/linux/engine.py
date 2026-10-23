#!/usr/bin/python3
"""IBus adapter. Run using the system Python that supplies python3-gi."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import gi
gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus
from claudish.composition import LABELS, MAX_COMPOSITION, MODES, Composition, ShiftTap
from claudish.client import Suggestions

# Pressed alone, these keys must not end the phrase. AltGr (Level3) types characters.
MODIFIER_KEYS = {getattr(IBus, "KEY_" + name) for name in (
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Super_L", "Super_R",
    "Meta_L", "Meta_R", "Hyper_L", "Hyper_R", "Caps_Lock", "Shift_Lock", "Num_Lock",
    "Scroll_Lock", "ISO_Level3_Shift", "ISO_Level5_Shift", "Mode_switch",
    "ISO_Next_Group", "ISO_Prev_Group")}



TRACE = os.environ.get("CLAUDISH_TRACE")  # a file path: event kinds, never typed text


def trace(*fields):
    if TRACE:
        with open(TRACE, "a") as out:
            out.write("%.3f %s\n" % (time.time(), " ".join(str(f) for f in fields)))


# The mode, as the input source indicator shows it.
SYMBOLS = {"continue": "C", "compose": "AI"}

# The field kinds IBus reports, by the names the service understands.
PURPOSES = {IBus.InputPurpose.TERMINAL: "terminal", IBus.InputPurpose.EMAIL: "email", IBus.InputPurpose.URL: "url",
            IBus.InputPurpose.NAME: "name", IBus.InputPurpose.NUMBER: "number", IBus.InputPurpose.PHONE: "phone",
            IBus.InputPurpose.DIGITS: "digits", IBus.InputPurpose.ALPHA: "alpha"}

class ClaudishEngine(IBus.Engine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.composition = Composition()
        self.shift = ShiftTap()  # Shift alone, tapped: the mode switch
        self.suggestions = Suggestions()
        self.sensitive = False
        self.app = None  # The focused program, for bindings ("supported text boxes").
        self.purpose = None  # The field's kind as the app reports it ("terminal", "email", ...).
        self.timer = GLib.timeout_add(40, self.poll)

    def poll(self):
        result = self.suggestions.poll()
        if result:
            revision, data = result
            trace("result", sorted(data), "current" if revision == self.composition.revision else "stale")
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
        if self.composition.live:
            # Continue: your words are in the app already; the preedit is only the greyed suggestion,
            # cleared (never committed) by a focus change.
            ghost = self.composition.ghost
            preedit = IBus.Text.new_from_string(ghost)
            if ghost:
                attributes = IBus.AttrList()
                attributes.append(IBus.attr_foreground_new(0x8A8A8A, 0, len(ghost)))
                preedit.set_attributes(attributes)
            self.update_preedit_text_with_mode(preedit, 0, bool(ghost), IBus.PreeditFocusMode.CLEAR)
            self.hide_lookup_table()
            self.update_auxiliary_text(IBus.Text.new_from_string("continue · Tab: take the rest · Esc: dismiss · "
                                                                 "F7: mode"), bool(ghost))
            return
        state = self.composition
        text = state.shown  # rewrite after Tab: the rewrite, in place of your words
        self.update_preedit_text_with_mode(IBus.Text.new_from_string(text), len(text), bool(text),
                                          IBus.PreeditFocusMode.COMMIT)
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
            hint = ("agent asks: %s · Enter: send your reply · Esc: clear it" % state.question.get("text", "")
                    if state.reply else
                    "agent asks: %s · 1–%d: choose, or type a reply · Esc: stop" % (state.question.get("text", ""),
                                                                                    len(state.question["choices"])))
        elif state.working and state.status:
            hint = "compose · %s · Esc: stop" % " ".join(state.status.split())[-90:]
        elif state.choosing:
            hint = ("compose · 1–%d: pick one · Enter: the first · Esc: back to the instruction"
                    % len(state.candidates))
        elif state.converted:
            hint = "compose · Tab: keep it · Esc: your words"
        elif state.candidate:
            hint = LABELS.get(state.asked or state.mode, "") + state.candidate
        elif state.working:
            hint = ("compose · rewriting… · Esc: your words" if state.asked == "rewrite" else
                    "compose · %s… · Esc: stop" % ("looking and working" if state.look else "working"))
        elif state.failed:
            hint = "compose · the request failed · Tab or Enter: try again · Esc: back"
        elif state.look:
            hint = "compose + window picture · Enter: send it as an instruction · F8: no picture"
        else:
            hint = ("compose · Tab: rewrite it · Enter: send it as an instruction · Shift+Enter: keep it"
                    " · Esc: drop it")
        self.update_auxiliary_text(IBus.Text.new_from_string(hint), bool(text))

    def changed(self):
        if self.composition.automatic:  # continue: the text so far is the context; what follows the caret too
            self.suggestions.schedule(self.composition.revision, self.composition.text, self.composition.mode,
                                      app=self.app, after=self.around_caret()[1][:500], purpose=self.purpose)
        elif not self.composition.text:
            self.suggestions.schedule(self.composition.revision, "")
        self.render()

    def around_caret(self):
        """(before, after): the app's text around the caret, when the client shares it (IBus
        surrounding text; GTK refreshes it before each key event). Empty when it does not."""
        if not getattr(self, "client_capabilities", 0) & IBus.Capabilite.SURROUNDING_TEXT:
            return "", ""
        try:
            text, cursor, _anchor = self.get_surrounding_text()
        except Exception:  # not every client implements it
            return "", ""
        value = text.get_text() if text else ""
        return value[:cursor], value[cursor:]

    def take_selection(self):
        """Rewrite with nothing composed: the app's selection becomes the composition (CJK input
        methods call it reconversion), removed from the app until you keep the rewrite or your
        words. Returns (before, after) around it, or None when there is no selection to take."""
        if not getattr(self, "client_capabilities", 0) & IBus.Capabilite.SURROUNDING_TEXT:
            return None
        try:
            text, cursor, anchor = self.get_surrounding_text()
        except Exception:
            return None
        value = text.get_text() if text else ""
        trace("selection", "cursor", cursor, "anchor", anchor, "length", len(value))
        start, end = min(cursor, anchor), max(cursor, anchor)
        if start == end or end - start > MAX_COMPOSITION:
            return None
        self.delete_surrounding_text(start - cursor, end - start)
        self.composition.adopt(value[start:end])
        return value[:start], value[end:]

    def before_caret(self):
        return self.around_caret()[0][-MAX_COMPOSITION:]

    def live_key(self, keyval):
        """Continue mode: keys go to the app as typed; Tab takes the suggestion, Esc dismisses it."""
        state = self.composition
        if keyval == IBus.KEY_Tab:
            ghost = state.take_ghost()
            if not ghost:
                return False  # no suggestion: Tab is the app's (next field, indent)
            self.changed()
            self.commit_text(IBus.Text.new_from_string(ghost))
            return True
        if keyval == IBus.KEY_Escape:
            if not state.ghost:
                return False
            state.dismiss()
            self.render()
            return True
        if keyval == IBus.KEY_BackSpace:
            if state.text:
                state.backspace()
                self.changed()
            return False  # the app deletes the character
        char = IBus.keyval_to_unicode(keyval)
        if char and char.isprintable():
            if not state.text:  # a fresh start (a click, a paste, a new field): begin from the app's text
                state.change(self.before_caret())
            typed = state.type_live(char)
            self.changed()
            self.commit_text(IBus.Text.new_from_string(typed))
            return True
        state.change("")  # Enter, arrows, anything else: the app's, and the context starts over
        self.changed()
        return False

    def finish(self, suggested=False):
        if self.composition.live:  # nothing is held back in continue mode: just start over
            self.composition.change("")
            self.changed()
            self.refresh_surrounding()
            return
        text = self.composition.commit(suggested)
        self.changed()
        if text:
            self.commit_text(IBus.Text.new_from_string(text))

    def do_process_key_event(self, keyval, keycode, state):
        # A Shift tap switches mode (continue <-> compose), as Shift switches English and pinyin.
        if keyval in (IBus.KEY_Shift_L, IBus.KEY_Shift_R) and not self.sensitive:
            if not state & IBus.ModifierType.RELEASE_MASK:
                self.shift.press(time.monotonic())
            elif self.shift.release(time.monotonic()):
                self.switch_mode()
            return False
        if not state & IBus.ModifierType.RELEASE_MASK:
            self.shift.other()
        if not state & IBus.ModifierType.RELEASE_MASK:
            name = IBus.keyval_name(keyval) or ""
            trace("key", name if len(name) > 1 else "char", self.composition.mode,
                  "ghost" if self.composition.ghost else "no-ghost", "rev", self.composition.revision)
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
        if self.composition.live:
            return self.live_key(keyval)
        if self.composition.question and not self.composition.reply and IBus.KEY_1 <= keyval <= IBus.KEY_9:
            chosen = self.composition.answer_choice(keyval - IBus.KEY_0)
            if chosen:
                self.suggestions.answer(*chosen)
                self.render()
            return True
        if self.composition.choosing and not self.composition.question and IBus.KEY_1 <= keyval <= IBus.KEY_9:
            text = self.composition.pick(keyval - IBus.KEY_0)
            if text is None:
                return True  # no such candidate: ignore the key rather than type it
            self.changed()
            self.commit_text(IBus.Text.new_from_string(text))
            return True
        if keyval in (IBus.KEY_Return, IBus.KEY_KP_Enter) and state & IBus.ModifierType.SHIFT_MASK:
            kept = self.composition.keep()  # Shift+Enter: as it is, and keep composing
            if not kept:
                return False
            self.changed()
            self.commit_text(IBus.Text.new_from_string(kept))
            return True
        if keyval in (IBus.KEY_Return, IBus.KEY_KP_Enter):
            action = self.composition.enter()
            if action == "reply":  # your own words, in answer to the agent's question
                session, question, words = self.composition.answer_text()
                self.suggestions.answer(session, question, text=words)
                self.render()
                return True
            if action == "submit":  # Instruct: Enter sends the held text now.
                self.composition.submit()
                before, after = self.around_caret()  # the text box, for this turn of its conversation
                self.suggestions.schedule(self.composition.revision, self.composition.text,
                                          "instruct", immediate=True, app=self.app,
                                          look=self.composition.look, before=before[-8000:], after=after[:8000],
                                          purpose=self.purpose)
                self.render()
            elif action in ("accept", "keep"):
                self.finish(action == "accept")
            return action != "pass"
        if keyval == IBus.KEY_Tab:
            around = None
            if not self.composition.live and not self.composition.text:
                around = self.take_selection()  # a selection: rewrite it in place
            action = self.composition.tab()
            if action == "accept":
                self.finish(True)
            elif action == "request":  # rewrite: ask now; it converts in place when it arrives
                before, after = around or self.around_caret()  # where the rewrite goes
                self.suggestions.schedule(self.composition.revision, self.composition.text, "rewrite",
                                          immediate=True, app=self.app, before=before[-1500:], after=after[:500],
                                          purpose=self.purpose)
                self.render()
            elif action == "convert":
                self.render()
            return action != "pass"
        if keyval == IBus.KEY_Escape:
            action = self.composition.escape()
            if action == "keep":
                self.finish()
            elif action == "clear":
                self.render()
            elif action in ("back", "drop"):
                # A pending answer or agent turn is for the old revision: stop it.
                self.suggestions.schedule(self.composition.revision, "")
                self.render()
            return action != "pass"
        if keyval == IBus.KEY_BackSpace:
            if not self.composition.text:
                return False
            self.composition.backspace()
            self.changed()
            return True
        char = IBus.keyval_to_unicode(keyval)
        if char and self.composition.passes(char):
            self.commit_text(IBus.Text.new_from_string(char))
            return True
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
        self.purpose = PURPOSES.get(purpose)
        # Not prose: suggestions only when asked for (Tab in rewrite, Enter in instruct).
        self.composition.quiet = self.purpose in ("url", "email", "number", "phone", "digits")
        if self.sensitive:
            self.do_reset()

    def switch_mode(self):
        """A Shift tap, or a pick from the indicator's menu: continue <-> compose. Leaving compose
        keeps what you see, as typed."""
        kept = self.composition.toggle()
        self.suggestions.schedule(self.composition.revision, "")  # what was asked belongs to the old mode
        if kept:
            self.commit_text(IBus.Text.new_from_string(kept))
        self.changed()
        self.show_mode()
        if not (self.composition.text or self.composition.ghost):  # say which mode, until the next key
            self.update_auxiliary_text(IBus.Text.new_from_string("cd_AI · " + self.composition.mode), True)

    def show_mode(self, register=False):
        """The mode in the desktop's input source indicator (GNOME shows an engine's InputMode
        property as the indicator's text), with a menu to pick one. The list is registered when a
        text box gets focus; a mode change updates the properties in it."""
        mode = self.composition.mode
        choices = [IBus.Property(key="mode." + name, prop_type=IBus.PropType.RADIO,
                                 label=IBus.Text.new_from_string(name), sensitive=True, visible=True,
                                 state=IBus.PropState.CHECKED if name == mode else IBus.PropState.UNCHECKED)
                   for name in MODES]
        menu = IBus.PropList()
        for choice in choices:
            menu.append(choice)
        current = IBus.Property(key="InputMode", prop_type=IBus.PropType.MENU,
                                label=IBus.Text.new_from_string("cd_AI · " + mode),
                                symbol=IBus.Text.new_from_string(SYMBOLS[mode]),
                                tooltip=IBus.Text.new_from_string("F7 switches mode"),
                                sensitive=True, visible=True, sub_props=menu)
        if register:
            properties = IBus.PropList()
            properties.append(current)
            self.register_properties(properties)
            return
        self.update_property(current)
        for choice in choices:
            self.update_property(choice)

    def do_property_activate(self, name, state):
        if name.startswith("mode.") and state == IBus.PropState.CHECKED and name[5:] in MODES:
            if self.composition.mode != name[5:]:
                self.switch_mode()

    def do_focus_in_id(self, object_path, client):
        # IBus 1.5.27+: client is "<im module>:<program>", for example "gtk3-im:firefox".
        self.app = None if client in ("", "fake") else client.split(":", 1)[-1]
        self.refresh_surrounding()
        self.show_mode(register=True)

    def do_focus_out(self):
        trace("focus-out")
        # IBus commits the visible preedit through PreeditFocusMode.COMMIT.
        self.do_reset()

    def do_disable(self):
        self.finish()

    def refresh_surrounding(self):
        """Ask the client for fresh surrounding text now; IBus answers a later read from its cache,
        so asking only when a key arrives returns stale text."""
        if getattr(self, "client_capabilities", 0) & IBus.Capabilite.SURROUNDING_TEXT:
            try:
                self.get_surrounding_text()
            except Exception:
                pass

    def do_reset(self):
        trace("reset")
        self.composition.change("")
        self.changed()
        self.refresh_surrounding()

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
