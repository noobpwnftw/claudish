#!/usr/bin/python3
"""IBus adapter. Run using the system Python that supplies python3-gi."""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import gi
gi.require_version("IBus", "1.0")
from gi.repository import Gio, GLib, IBus
from claudish.composition import MAX_COMPOSITION, MODES, Composition, ShiftTap
from claudish.client import Suggestions
from claudish.screen import is_terminal

# Dead keys (an accent, then the letter it goes on): IBus hands the engine the keysym, so composing
# them is the engine's job, as IBusEngineSimple does. keysym name -> (combining mark, spacing accent).
DEAD_KEYS = {"dead_grave": ("\u0300", "`"), "dead_acute": ("\u0301", "´"), "dead_circumflex": ("\u0302", "^"),
             "dead_tilde": ("\u0303", "~"), "dead_macron": ("\u0304", "¯"), "dead_breve": ("\u0306", "˘"),
             "dead_abovedot": ("\u0307", "˙"), "dead_diaeresis": ("\u0308", "¨"), "dead_abovering": ("\u030a", "˚"),
             "dead_doubleacute": ("\u030b", "˝"), "dead_caron": ("\u030c", "ˇ"), "dead_cedilla": ("\u0327", "¸"),
             "dead_ogonek": ("\u0328", "˛")}


def with_accent(dead, char):
    """The character a dead key and the next key make: é from ´ and e, the accent alone before a
    space or the same dead key, else the accent and then the character."""
    mark, spacing = DEAD_KEYS[dead]
    if char in (" ", spacing):
        return spacing
    import unicodedata
    composed = unicodedata.normalize("NFC", char + mark)
    return composed if len(composed) == 1 else spacing + char

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
SYMBOLS = {"continue": "cd", "compose": "AI"}  # the top bar: the brand while it stays out of the way, AI in compose

# The field kinds IBus reports, by the names the service understands.
PURPOSES = {IBus.InputPurpose.TERMINAL: "terminal", IBus.InputPurpose.EMAIL: "email", IBus.InputPurpose.URL: "url",
            IBus.InputPurpose.NAME: "name", IBus.InputPurpose.NUMBER: "number", IBus.InputPurpose.PHONE: "phone",
            IBus.InputPurpose.DIGITS: "digits", IBus.InputPurpose.ALPHA: "alpha"}

SCREEN_XML = """<node><interface name="io.claudish.Screen">
  <method name="Get"><arg type="s" direction="out"/></method>
  <signal name="Changed"><arg type="s"/></signal>
</interface></node>"""


class Screen:
    """What cd_AI shows at the caret, for cd_AI's GNOME Shell extension to draw
    (platforms/linux/gnome-extension): the panel (Composition.panel()), continue's suggestion, and
    the mode switch, as JSON on the session bus. The extension owns io.claudish.Shell; while it
    does, the engine draws nothing with IBus's own popup. Elsewhere (no GNOME Shell, or no
    extension), IBus's popup shows the rows and the hint as plain text."""

    def __init__(self):
        self.shell, self.state, self.shown, self.toasting = False, "{}", {}, False
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            info = Gio.DBusNodeInfo.new_for_xml(SCREEN_XML).interfaces[0]
            self.bus.register_object("/io/claudish/Screen", info, self.call, None, None)
            Gio.bus_own_name_on_connection(self.bus, "io.claudish.Screen", Gio.BusNameOwnerFlags.NONE, None, None)
            Gio.bus_watch_name_on_connection(self.bus, "io.claudish.Shell", Gio.BusNameWatcherFlags.NONE,
                                             lambda *_: self.watch(True), lambda *_: self.watch(False))
        except GLib.Error as error:  # no session bus: IBus's popup only
            trace("screen bus", error.message)
            self.bus = None

    def watch(self, present):
        trace("shell extension", "present" if present else "absent")
        self.shell = present

    def call(self, connection, sender, path, interface, method, parameters, invocation):
        invocation.return_value(GLib.Variant("(s)", (self.state,)))

    def publish(self, panel=None, ghost="", toast=None):
        """What is at the caret. A toast stays until its time is up or a key ends it (False)."""
        self.toasting = bool(toast) or (self.toasting and toast is None)
        self.shown = {"panel": panel, "ghost": ghost}
        self.state = json.dumps({**self.shown, "toast": toast})
        if self.bus is not None:
            self.bus.emit_signal(None, "/io/claudish/Screen", "io.claudish.Screen", "Changed",
                                 GLib.Variant("(s)", (self.state,)))

    def end_toast(self):
        """A key ends a toast: it was said where the caret was."""
        if self.toasting:
            self.publish(**self.shown, toast=False)


SCREEN = None


def open_settings():
    """cd_AI's settings in the browser, the same page on every OS. Asking the service for the page's
    link happens off the main loop: typing never waits on it."""
    import subprocess
    import threading
    from claudish.client import settings_url

    def open_it():
        try:
            subprocess.run(["xdg-open", settings_url()], check=False, timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as error:
            trace("settings failed", type(error).__name__)
    threading.Thread(target=open_it, daemon=True).start()


def screen():
    global SCREEN
    if SCREEN is None:
        SCREEN = Screen()
    return SCREEN


class ClaudishEngine(IBus.Engine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.composition = Composition()
        self.shift = ShiftTap()  # Shift alone, tapped: the mode switch
        self.suggestions = Suggestions()
        self.sensitive = False
        self.app = None  # The focused program, for bindings ("supported text boxes").
        self.purpose = None  # The field's kind as the app reports it ("terminal", "email", ...).
        self.drawn = None  # the panel as last shown, redrawn when the state's description changes
        self.timer = GLib.timeout_add(40, self.poll)

    def poll(self):
        if self.composition.follow(self.suggestions):  # the service stopped or came back
            if self.composition.text and not self.composition.live:
                self.render()
        result = self.suggestions.poll()
        if result:
            revision, data = result
            trace("result", sorted(data), "current" if revision == self.composition.revision else "stale")
            kind = self.composition.receive(revision, data)
            if kind:  # a draft, a question, progress; done: nothing to insert
                self.render()
            toast = self.composition.done_toast(data["done"]) if kind == "done" else None
            if toast and screen().shell:
                screen().publish(self.drawn, "", toast)
        if not self.composition.live and self.composition.panel() != self.drawn:
            self.render()  # the pause before compose's keys, or anything else the description shows
        return True

    def render(self):
        state = self.composition
        panel = None if state.live else state.panel()
        self.drawn = panel
        if screen().shell:
            # cd_AI's GNOME Shell extension draws the panel and the suggestion (the design lab's
            # GNOME mock); IBus keeps only the composition, as the platform's plain preedit.
            text = "" if state.live else state.shown
            self.update_preedit_text_with_mode(IBus.Text.new_from_string(text), len(text), bool(text),
                                              self.focus_mode())
            self.hide_lookup_table()
            self.update_auxiliary_text(IBus.Text.new_from_string(""), False)
            screen().publish(panel, state.ghost if state.live and not state.inside else "")
            return
        if state.live:
            # Continue: your words are in the app already; the preedit is only the greyed suggestion,
            # cleared (never committed) by a focus change.
            ghost = state.ghost
            preedit = IBus.Text.new_from_string(ghost)
            if ghost:
                attributes = IBus.AttrList()
                attributes.append(IBus.attr_foreground_new(0x8A8A8A, 0, len(ghost)))
                preedit.set_attributes(attributes)
            self.update_preedit_text_with_mode(preedit, 0, bool(ghost), IBus.PreeditFocusMode.CLEAR)
            self.hide_lookup_table()
            self.update_auxiliary_text(IBus.Text.new_from_string(""), False)  # quiet: the suggestion speaks
            return
        text = state.shown  # your words (a rewrite waits in the panel), or a reply once sent
        self.update_preedit_text_with_mode(IBus.Text.new_from_string(text), len(text), bool(text),
                                          self.focus_mode())
        # IBus's own popup (without the extension): the rows as a list, the rest as one line. No
        # numbers: digits are text here, they pick nothing (as on Windows).
        if panel and panel["rows"]:
            table = IBus.LookupTable.new(9, 0, True, False)
            for index, row in enumerate(panel["rows"]):
                table.append_candidate(IBus.Text.new_from_string(
                    row["text"] + (" — " + row["legend"] if row.get("legend") else "")))
                table.set_label(index, IBus.Text.new_from_string(""))
            table.set_cursor_visible(panel["on"] >= 0)  # an approval highlights nothing until ↓; then Tab takes it
            self.update_lookup_table(table, True)
        else:
            self.hide_lookup_table()
        hint = state.hint()  # the panel's words as one line
        self.update_auxiliary_text(IBus.Text.new_from_string(hint), bool(text and hint))

    def focus_mode(self):
        """What IBus does with the preedit when focus leaves: words you are typing are committed, as
        a CJK input method's are; a sent instruction (or a reply to the model) is cleared, held with
        its exchange for Shift+Esc."""
        return IBus.PreeditFocusMode.CLEAR if self.composition.sent else IBus.PreeditFocusMode.COMMIT

    def changed(self):
        after = self.around_caret()[1] if self.composition.live else ""
        self.composition.inside = bool(after.split("\n", 1)[0].strip())  # continue waits for a line's end
        if self.composition.automatic:  # continue: the text so far is the context; what follows the caret too
            self.suggestions.schedule(self.composition.revision, self.composition.text, self.composition.mode,
                                      app=self.app, after=after[:500], purpose=self.purpose)
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
        """Tab with nothing composed: the app's selection becomes the composition, as if you had just
        typed it; then Tab rewrites it, Shift+Enter sends it. Nothing is deleted: input replaces a
        selection, as typing does (Qt removes it as the composition starts, then would apply a
        deletion's offset from the new caret). True when taken."""
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
        self.composition.change(value[start:end])
        return True

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
            state.type_live(char)  # continue types exactly the key: the app inserts it itself
            self.changed()
            # Passed on rather than committed: the app then reports its caret after the key (a
            # commit from here leaves the reported caret one character behind, and the suggestion
            # would be drawn over the space you just typed).
            return False
        state.change("")  # Enter, arrows, anything else: the app's, and the context starts over
        self.changed()
        return False

    def finish(self, suggested=False):
        self.dead = None  # an accent waiting for its letter goes with the composition
        if self.composition.live:  # nothing is held back in continue mode: just start over
            self.composition.change("")
            self.changed()
            self.refresh_surrounding()
            return
        if self.composition.sent and not suggested:
            # A shortcut or another key ends the composition: the instruction is not text for the
            # app; its exchange is held for this app, its work going on, as on a focus change.
            self.composition.leave(self.app)
            self.render()
            return
        text = self.composition.commit(suggested)
        if text:
            self.commit_text(IBus.Text.new_from_string(text))
        self.changed()  # after it: words that stay are the next composition

    def do_process_key_event(self, keyval, keycode, state):
        # A Shift tap switches mode (continue <-> compose), as Shift switches English and pinyin.
        if keyval in (IBus.KEY_Shift_L, IBus.KEY_Shift_R) and not self.sensitive:
            chord = bool(state & (IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.MOD1_MASK |
                                  IBus.ModifierType.SUPER_MASK | IBus.ModifierType.META_MASK))
            if not state & IBus.ModifierType.RELEASE_MASK:
                self.shift.press(time.monotonic(), chord)
            elif self.shift.release(time.monotonic(), chord):
                self.switch_mode()
            return False
        if not state & IBus.ModifierType.RELEASE_MASK:
            self.shift.other()
            screen().end_toast()
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
        if keyval == IBus.KEY_F8 and self.composition.toggle_look():
            self.render()
            return True
        if self.composition.live:
            return self.live_key(keyval)
        # Choices are not numbered: digits are text in English, as Space is (↑/↓, then Tab).
        shift = bool(state & IBus.ModifierType.SHIFT_MASK)
        if keyval in (IBus.KEY_Return, IBus.KEY_KP_Enter) and not self.composition.talks(shift):
            kept = self.composition.keep()  # the keeper key: as it is, and keep composing
            if kept is None:  # the model is asked: taken, nothing goes in
                self.render()
                return True
            if not kept:
                return False
            self.changed()
            self.commit_text(IBus.Text.new_from_string(kept))
            return True  # Enter commits, as other input methods do: press it again for the app
        if keyval in (IBus.KEY_Return, IBus.KEY_KP_Enter):
            action = self.composition.enter()
            if action == "reply":  # your own words, in answer to the agent's question
                session, question, words = self.composition.answer_text()
                self.suggestions.answer(session, question, text=words)
                self.render()
                return True
            if action == "submit":  # Instruct: Shift+Enter sends the held text now.
                self.composition.submit()
                before, after = self.around_caret()  # the text box, for this turn of its conversation
                self.suggestions.schedule(self.composition.revision, self.composition.text,
                                          "instruct", immediate=True, app=self.app,
                                          look=self.composition.look, before=before[-8000:], after=after[:8000],
                                          purpose=self.purpose, draft=self.composition.about)
                self.render()
            elif action == "wait":  # on the model's text, the panel lights Tab, the key that takes it
                self.render()
            return action != "pass"
        if keyval == IBus.KEY_Tab:
            if not self.composition.live and not self.composition.text and self.take_selection():
                self.render()  # a selection: your words now, as if typed
                return True
            action = self.composition.tab()
            if action == "choose":
                chosen = self.composition.answer_choice()
                if chosen:
                    self.suggestions.answer(*chosen)
                self.render()
                return True
            if action == "accept":
                answering = self.composition.take_answering()  # an answer to read: recorded, not asked again
                if answering:
                    self.suggestions.answer(*answering)
                self.finish(True)
            elif action == "request":  # rewrite: ask now; it waits in the panel when it arrives
                before, after = self.around_caret()  # where the rewrite goes
                self.suggestions.schedule(self.composition.revision, self.composition.text, "rewrite",
                                          immediate=True, app=self.app, before=before[-1500:], after=after[:500],
                                          purpose=self.purpose)
                self.render()
            elif action == "convert":
                self.render()
            return action != "pass"
        if keyval in (IBus.KEY_Up, IBus.KEY_Down) and self.composition.move(-1 if keyval == IBus.KEY_Up else 1):
            self.render()  # ↑ and ↓ move the highlight
            return True
        if keyval == IBus.KEY_Escape and state & IBus.ModifierType.SHIFT_MASK and self.composition.restore():
            # A held exchange's request is still running: its results come for the same revision.
            self.render()  # Shift+Esc: what Esc dropped, or the exchange you left, back
            return True
        if keyval == IBus.KEY_Escape:
            action = self.composition.escape()
            if action == "dismiss":  # an answer to read: Dismiss, nothing inserted
                chosen = self.composition.dismissal()
                if chosen:
                    self.suggestions.answer(*chosen)
                self.render()
                return True
            toast = self.composition.dropped_toast() if action in ("clear", "drop") else None
            if toast and screen().shell:  # said, with the key that brings it back
                screen().publish(None, "", toast)
            if action == "clear":
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
        name = IBus.keyval_name(keyval) or ""
        if name in DEAD_KEYS:  # an accent waits for its letter
            if getattr(self, "dead", None):
                char = DEAD_KEYS[self.dead][1] if name == self.dead else None
                self.dead = None if char else name
                if char:
                    self.composition.insert(char)
                    self.changed()
            else:
                self.dead = name
            return True
        char = IBus.keyval_to_unicode(keyval)
        if getattr(self, "dead", None) and char:
            char, self.dead = with_accent(self.dead, char), None
            if len(char) > 1:  # no such letter: the accent, then the key
                self.composition.insert(char[0])
                char = char[1:]
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
        self.update_quiet()
        if self.sensitive:
            self.do_reset()

    def update_quiet(self):
        """Not prose (a URL, an address, a number, a terminal's command line): nothing unasked;
        Tab and Shift+Enter in compose still ask."""
        self.composition.field(self.purpose, self.purpose == "terminal" or is_terminal(self.app))

    def switch_mode(self):
        """A Shift tap, or a pick from the indicator's menu: continue <-> compose. Leaving compose
        keeps what you see, as typed."""
        kept = self.composition.toggle()
        self.suggestions.schedule(self.composition.revision, "")  # what was asked belongs to the old mode
        if kept:
            self.commit_text(IBus.Text.new_from_string(kept))
        self.changed()
        self.show_mode()
        spec, lasting = self.composition.switched()
        if not (self.composition.hints or lasting):
            return
        if screen().shell:  # the mode switch briefly at the caret, or the held exchange's pill
            screen().publish(self.drawn, "", spec)
        elif not (self.composition.text or self.composition.ghost):  # say which mode, until the next key
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
                                tooltip=IBus.Text.new_from_string("Tap Shift to switch"),
                                sensitive=True, visible=True, sub_props=menu)
        if register:
            properties = IBus.PropList()
            properties.append(current)
            properties.append(IBus.Property(key="settings", prop_type=IBus.PropType.NORMAL,
                                            label=IBus.Text.new_from_string("Settings…"),
                                            tooltip=IBus.Text.new_from_string("The model, its key, the tone"),
                                            sensitive=True, visible=True))
            self.register_properties(properties)
            return
        self.update_property(current)
        for choice in choices:
            self.update_property(choice)

    def do_property_activate(self, name, state):
        if name == "settings":
            open_settings()
            return
        if name.startswith("mode.") and state == IBus.PropState.CHECKED and name[5:] in MODES:
            if self.composition.mode != name[5:]:
                self.switch_mode()

    def do_focus_in_id(self, object_path, client):
        # IBus 1.5.27+: client is "<im module>:<program>", for example "gtk3-im:firefox".
        self.app = None if client in ("", "fake") else client.split(":", 1)[-1]
        # One conversation per text box (its input context), as on Windows: earlier instructions,
        # context and approvals stay with the box they were made in.
        if getattr(self, "context", None) not in (None, object_path):
            self.suggestions.new_conversation(end=self.composition.held is None)  # a held exchange goes on
        self.context = object_path
        self.update_quiet()
        self.refresh_surrounding()
        self.show_mode(register=True)
        pill = self.composition.returned(self.app)  # back where an exchange was held: a pill, no keys
        if pill and screen().shell:
            screen().publish(None, "", pill)

    def do_focus_out(self):
        trace("focus-out")
        if self.composition.sent:  # an instruction's exchange: held for this app, its work going on
            self.composition.leave(self.app)
            self.render()
            return
        # IBus commits the visible preedit (words you were typing) through PreeditFocusMode.COMMIT.
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
        if self.composition.sent:  # a click in the field: the exchange is held, as on a focus change
            self.composition.leave(self.app)
            self.render()
            return
        self.composition.change("")
        self.changed()
        self.refresh_surrounding()

    def do_destroy(self):
        screen().publish()  # nothing at the caret
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
