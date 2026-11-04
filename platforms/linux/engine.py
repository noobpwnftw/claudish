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
from claudish.composition import AROUND, MAX_COMPOSITION, MODES, Composition, ShiftTap, accented, typeable, window
from claudish.client import Suggestions
from claudish.screen import is_terminal

# Dead keys (an accent, then the letter it goes on): IBus hands the engine the keysym, so composing
# them is the engine's job, as IBusEngineSimple does. keysym name -> its spacing accent (a key of composition.ACCENTS).
DEAD_KEYS = {"dead_grave": "`", "dead_acute": "´", "dead_circumflex": "^", "dead_tilde": "~", "dead_macron": "¯",
             "dead_breve": "˘", "dead_abovedot": "˙", "dead_diaeresis": "¨", "dead_abovering": "˚",
             "dead_doubleacute": "˝", "dead_caron": "ˇ", "dead_cedilla": "¸", "dead_ogonek": "˛"}
DEAD_BY_ACCENT = {accent: name for name, accent in DEAD_KEYS.items()}


# By keyval: IBus names some keys otherwise (dead_tilde is dead_perispomeni to IBus 1.5.29).
DEAD_BY_KEYVAL = {IBus.keyval_from_name(name): name for name in DEAD_KEYS}
COMPOSER = []  # the Compose key's table (claudish/x11_compose.py), read at its first use


def compared(keyval):
    """A key as the Compose table compares it: the character it types, else its keyval (the files
    and IBus name keys differently: <U01A1>, ohorn and U+01A1 are one key)."""
    return IBus.keyval_to_unicode(keyval) or keyval


def composer():
    if not COMPOSER:
        from claudish.x11_compose import Compose
        COMPOSER.append(Compose(key=lambda name: (lambda keyval: None if keyval in (0, IBus.KEY_VoidSymbol)
                                                  else compared(keyval))(IBus.keyval_from_name(name))))
    return COMPOSER[0]


def key_name(keyval):
    return DEAD_BY_KEYVAL.get(keyval) or IBus.keyval_name(keyval) or ""


# Held with a key, these make it a shortcut: the app's, and the composition ends.
SHORTCUT_MASK = (IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.MOD1_MASK |
                 IBus.ModifierType.SUPER_MASK | IBus.ModifierType.META_MASK)
STEPS = {IBus.KEY_Left: -1, IBus.KEY_Right: 1, IBus.KEY_Home: "home", IBus.KEY_End: "end",
         IBus.KEY_KP_Left: -1, IBus.KEY_KP_Right: 1, IBus.KEY_KP_Home: "home", IBus.KEY_KP_End: "end"}

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
  <method name="Focus"><arg type="s" direction="in"/><arg type="s" direction="in"/></method>
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
        # GNOME on Wayland gives IBus one input context for every app: the extension says which
        # window (and app) has focus, and the engine in that context follows it (on_focus).
        self.focus, self.on_focus = None, None
        self.on_presence = None  # the focused engine: it draws again where the extension is, or is not
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
        changed, self.shell = present != self.shell, present
        if changed and self.on_presence is not None:
            # Disabled, or the shell restarted: the panel and suggestion go to IBus's popup and
            # preedit; back, the extension gets what is at the caret now, and IBus's are cleared.
            self.on_presence()

    def call(self, connection, sender, path, interface, method, parameters, invocation):
        if method == "Focus":
            before, self.focus = self.focus, tuple(parameters.unpack())  # (app, window)
            trace("window", self.focus[0])
            invocation.return_value(None)
            if self.on_focus is not None:  # the same window again: its class came, the window did not change
                self.on_focus(same=bool(before) and before[1] == self.focus[1] and bool(self.focus[1]))
            return
        invocation.return_value(GLib.Variant("(s)", (self.state,)))

    def publish(self, panel=None, ghost="", toast=None, lasting=False):
        """What is at the caret. A toast stays until its time is up or a key ends it (False);
        lasting (the held exchange's pill): until a key."""
        self.toasting = bool(toast) or (self.toasting and toast is None)
        self.shown = {"panel": panel, "ghost": ghost}
        self.state = json.dumps({**self.shown, "toast": toast, "lasting": bool(toast and lasting)})
        if self.bus is not None:
            self.bus.emit_signal(None, "/io/claudish/Screen", "io.claudish.Screen", "Changed",
                                 GLib.Variant("(s)", (self.state,)))

    def end_toast(self):
        """A key ends a toast: it was said where the caret was."""
        if self.toasting:
            self.publish(**self.shown, toast=False)


SCREEN = None


def open_settings():
    """cd_AI's settings in the browser (claudish.client.show_settings)."""
    import subprocess
    from claudish.client import show_settings
    show_settings(lambda link: subprocess.run(["xdg-open", link], check=False, timeout=10,
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
                  lambda error: trace("settings failed", type(error).__name__))


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
        self.focused = True  # until IBus says otherwise: an engine may start in a box that has focus
        # The client's object path, GNOME's shared one, a Compose key's sequence, and the path IBus
        # 1.5.26 (no focus ids) gives this engine.
        self.context = self.shared = self.sequence = self.own_path = None

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
            text = state.accent if state.live else state.drawn  # continue: only a waiting accent
            cursor = len(text) if state.live else state.drawn_cursor  # continue: after the accent
            self.update_preedit_text_with_mode(IBus.Text.new_from_string(text), cursor if text else 0, bool(text),
                                              self.focus_mode())
            self.hide_lookup_table()
            self.update_auxiliary_text(IBus.Text.new_from_string(""), False)
            screen().publish(panel, state.ghost if state.live and not state.inside else "")
            return
        if state.live:
            # Continue: your words are in the app already; the preedit is a waiting accent and the
            # greyed suggestion, cleared (never committed) by a focus change.
            accent, ghost = state.accent, state.ghost
            preedit = IBus.Text.new_from_string(accent + ghost)
            if ghost:
                attributes = IBus.AttrList()
                attributes.append(IBus.attr_foreground_new(0x8A8A8A, len(accent), len(accent) + len(ghost)))
                preedit.set_attributes(attributes)
            self.update_preedit_text_with_mode(preedit, len(accent), bool(accent or ghost), IBus.PreeditFocusMode.CLEAR)
            self.hide_lookup_table()
            self.update_auxiliary_text(IBus.Text.new_from_string(""), False)  # quiet: the suggestion speaks
            return
        text = state.drawn  # your words (a rewrite waits in the panel), or a reply once sent; a waiting accent
        self.update_preedit_text_with_mode(IBus.Text.new_from_string(text), state.drawn_cursor if text else 0, bool(text),
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
            table.set_cursor_pos(max(panel["on"], 0))  # the row Tab takes, as the other platforms draw it
            self.update_lookup_table(table, True)
        else:
            self.hide_lookup_table()
        hint = state.hint()  # the panel's words as one line
        self.update_auxiliary_text(IBus.Text.new_from_string(hint), bool(text and hint))

    def focus_mode(self):
        """What IBus does with the preedit when focus leaves: words you are typing are committed, as
        a CJK input method's are; a sent instruction (or a reply to the model) is cleared, held with
        its exchange for Shift+Esc."""
        state = self.composition
        # A waiting accent alone is not typed text: it goes with the focus, as the OS's own does (in
        # continue, your words are in the app already: the preedit is never typed text).
        return IBus.PreeditFocusMode.CLEAR if state.for_model or state.live or not state.shown \
            else IBus.PreeditFocusMode.COMMIT

    def changed(self):
        after = self.composition.caret_after(self.around_caret()[1] if self.composition.live else "")
        if self.composition.automatic:  # continue: the text so far is the context; what follows the caret too
            self.suggestions.schedule(self.composition.revision, self.composition.text, self.composition.mode,
                                      app=self.app, after=after, purpose=self.purpose)
        elif not self.composition.text:
            self.suggestions.schedule(self.composition.revision, "")
        self.render()

    def surrounding(self):
        """(text, cursor, anchor): the app's text around the caret, when the client shares it (IBus
        surrounding text; GTK refreshes it before each key event), else None. Asking also makes
        IBus fetch it fresh: it answers a later read from its cache."""
        if not getattr(self, "client_capabilities", 0) & IBus.Capabilite.SURROUNDING_TEXT:
            return None
        try:
            text, cursor, anchor = self.get_surrounding_text()
        except Exception:  # not every client implements it
            return None
        return (text.get_text() if text else ""), cursor, anchor

    def around_caret(self):
        """(before, after): the app's text around the caret; empty when the client does not share it."""
        found = self.surrounding()
        if not found:
            return "", ""
        value, cursor, _anchor = found
        return value[:cursor], value[cursor:]

    def take_selection(self):
        """Tab with nothing composed: the app's selection becomes the composition, as if you had just
        typed it; then Tab rewrites it, Shift+Enter sends it. Nothing is deleted: input replaces a
        selection, as typing does (Qt removes it as the composition starts, then would apply a
        deletion's offset from the new caret). True when taken."""
        found = self.surrounding()
        if not found:
            return None
        value, cursor, anchor = found
        trace("selection", "cursor", cursor, "anchor", anchor, "length", len(value))
        start, end = min(cursor, anchor), max(cursor, anchor)
        if not self.composition.selectable(value[start:end]):  # long or multi-line: Tab is the app's
            return None
        self.composition.change(value[start:end])
        return True

    def before_caret(self):
        return self.around_caret()[0][-MAX_COMPOSITION:]

    def live_key(self, keyval):
        """Continue mode: keys go to the app as typed; Tab takes the suggestion, Esc dismisses it."""
        state = self.composition
        name = self.compose_key(keyval)
        if name is None:
            return True
        if name in DEAD_KEYS:  # an accent waits for its letter, as in compose (drawn at the caret)
            if self.dead:  # the same one again types it alone; another takes its place
                accent, self.dead = DEAD_KEYS[self.dead], (None if name == self.dead else name)
                if not self.dead:
                    self.live_commit(accent)
            else:
                self.dead = name
            self.render()
            return True
        char = IBus.keyval_to_unicode(keyval)
        if self.dead and typeable(char):
            combined, self.dead = accented(self.composition.accent, char), None
            self.live_commit(combined)  # é goes in, not the e the key would type
            return True
        if keyval == IBus.KEY_Tab:
            if state.ghost and not state.caret_stayed(self.around_caret()[0]):  # a click moved it (no reset)
                state.dismiss()
                self.render()
                return False
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

    def live_commit(self, text):
        """Continue: text the input method puts in itself (an accented letter), as typed."""
        if not self.composition.text:
            self.composition.change(self.before_caret())
        for char in text:
            self.composition.type_live(char)
        self.commit_text(IBus.Text.new_from_string(text))
        self.changed()

    def finish(self, suggested=False):
        self.dead = None  # an accent waiting for its letter goes with the composition
        self.sequence = None  # and a Compose key's sequence
        if self.composition.live:  # nothing is held back in continue mode: just start over
            self.composition.change("")
            self.changed()
            self.refresh_surrounding()
            return
        # A shortcut or another key ends the composition: the instruction is not text for the app;
        # its exchange is held for this text box, its work going on, as on a focus change.
        if not suggested and self.hold():
            return
        text = self.composition.commit(suggested)
        if text:
            self.commit_text(IBus.Text.new_from_string(text))
        self.changed()  # after it: words that stay are the next composition

    def type_in(self, text):
        """What a key typed (an accent with it): to the app when it all passes (punctuation with
        nothing composed), else into the composition; full, what is before the cursor goes in first."""
        if all(self.composition.passes(char) for char in text):
            self.commit_text(IBus.Text.new_from_string(text))
            self.changed()  # the accent it waited with is no longer drawn
            return True
        for char in text:
            if not self.composition.insert(char):  # full: what is before the cursor goes in
                self.commit_text(IBus.Text.new_from_string(self.composition.make_room(char)))
        self.changed()
        return True

    def compose_key(self, keyval):
        """The key's name; None for the Compose key, or a dead key the accents here do not draw
        (Vietnamese's dead_belowdot, dead_hook): taken, its sequence waits for what follows, as the
        compose table makes it."""
        name = key_name(keyval)
        if name == "Multi_key":
            self.sequence = []
            return None
        if name.startswith("dead_") and name not in DEAD_KEYS and composer().step([compared(keyval)])[0] == "wait":
            self.sequence = [compared(keyval)]
            return None
        return name

    def compose_next(self, keyval):
        """A key while the Compose key's sequence waits, as GTK's: Backspace takes back its last
        key, Esc ends it, and a key it cannot go on with ends it and is dropped; one that types
        nothing (Enter, Tab, an arrow) then does its own (None)."""
        if keyval == IBus.KEY_BackSpace:
            self.sequence = self.sequence[:-1] if self.sequence else None
            return True
        if keyval == IBus.KEY_Escape:
            self.sequence = None
            return True
        key = compared(keyval)
        kind, text = composer().step(self.sequence + [key])
        if kind == "wait":
            self.sequence.append(key)
            return True
        self.sequence = None
        if kind == "text":
            if self.composition.live:
                self.live_commit(text)
                return True
            return self.type_in(text)
        return True if typeable(IBus.keyval_to_unicode(keyval)) else None

    @property
    def dead(self):
        """The dead key whose accent waits for its letter (the composition's accent, drawn there), or
        None: every change clears the accent (a focus change, a reset, a Shift tap, a result), so it
        never lands on a letter typed later."""
        return DEAD_BY_ACCENT.get(self.composition.accent)

    @dead.setter
    def dead(self, name):
        self.composition.accent = DEAD_KEYS[name] if name else ""

    def do_process_key_event(self, keyval, keycode, state):
        # A Shift tap switches mode (continue <-> compose), as Shift switches English and pinyin.
        if keyval in (IBus.KEY_Shift_L, IBus.KEY_Shift_R) and not self.sensitive:
            chord = bool(state & SHORTCUT_MASK)
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
        if self.dead and key_name(keyval) not in DEAD_KEYS \
                and not typeable(IBus.keyval_to_unicode(keyval)):
            self.dead = None  # an accent waiting for its letter: any other key cancels it, as GTK's does
            self.render()
            if keyval in (IBus.KEY_BackSpace, IBus.KEY_Escape):
                return True  # Backspace or Esc cancels the accent, and nothing else
        if state & SHORTCUT_MASK:
            self.finish()
            return False
        if self.sequence is not None:  # the Compose key's sequence takes it first
            handled = self.compose_next(keyval)
            if handled is not None:
                return handled
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
                                          look=self.composition.look, before=before[-AROUND:], after=after[:AROUND],
                                          purpose=self.purpose, draft=self.composition.about)
                self.render()
            elif action == "wait":  # on the model's text, the panel lights Tab, the key that takes it
                self.render()
            return action != "pass"
        if keyval == IBus.KEY_Tab:
            if not self.composition.text and self.take_selection():  # (continue returned above)
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
                before, after = window(*self.around_caret())  # where the rewrite goes, as much as it sends
                self.suggestions.schedule(self.composition.revision, self.composition.text, "rewrite",
                                          immediate=True, app=self.app, before=before, after=after,
                                          purpose=self.purpose)
                self.render()
            elif action == "convert":
                self.render()
            return action != "pass"
        if keyval in (IBus.KEY_Up, IBus.KEY_Down) and self.composition.move(-1 if keyval == IBus.KEY_Up else 1):
            self.render()  # ↑ and ↓ move the highlight
            return True
        if keyval == IBus.KEY_Escape and state & IBus.ModifierType.SHIFT_MASK:
            if self.composition.restore():
                # A held exchange's request is still running: its results come for the same revision.
                self.render()  # Shift+Esc: what Esc dropped, or the exchange you left, back
                return True
            if self.composition.text:
                return True  # composing, it brings nothing back, and never drops what you typed
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
        plain = not state & (IBus.ModifierType.SHIFT_MASK | IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.MOD1_MASK)
        if keyval in STEPS and plain and self.composition.arrow(STEPS[keyval]):
            self.sequence = None  # a Compose key waiting is for the key right after it
            self.changed()  # ← → move in what you type, as a CJK composition does
            return True
        if keyval in (IBus.KEY_Delete, IBus.KEY_KP_Delete) and plain and self.composition.delete():  # forward delete
            self.sequence = None
            self.changed()
            return True
        name = self.compose_key(keyval)
        if name is None:
            return True
        if name in DEAD_KEYS:  # an accent waits for its letter
            if self.dead:
                char = DEAD_KEYS[self.dead] if name == self.dead else None
                self.dead = None if char else name
                if char:
                    return self.type_in(char)
            else:
                self.dead = name
            self.render()  # the accent shows where it waits
            return True
        char = IBus.keyval_to_unicode(keyval)
        if self.dead and char:
            char, self.dead = accented(self.composition.accent, char), None  # no such letter: the accent, then the key
        if char and all(typeable(each) for each in char):  # not Delete's DEL, nor another control
            return self.type_in(char)
        self.finish()
        return False

    def do_set_content_type(self, purpose, hints):
        self.sensitive = purpose in (IBus.InputPurpose.PASSWORD, IBus.InputPurpose.PIN)
        self.purpose = PURPOSES.get(purpose)
        self.update_quiet()
        if self.sensitive:
            self.finish()  # words typed before it became a password field go in, as on a focus change

    def update_quiet(self):
        """Not prose (a URL, an address, a number, a terminal's command line): nothing unasked;
        Tab and Shift+Enter in compose still ask."""
        self.composition.field(self.purpose, self.purpose == "terminal" or is_terminal(self.app))

    def switch_mode(self):
        """A Shift tap, or a pick from the indicator's menu: continue <-> compose. Leaving compose
        keeps what you see, as typed."""
        kept = self.composition.toggle()
        self.sequence = None  # a Compose key waiting belongs to the old mode
        self.suggestions.schedule(self.composition.revision, "")  # what was asked belongs to the old mode
        if kept:
            self.commit_text(IBus.Text.new_from_string(kept))
        self.changed()
        self.show_mode()
        spec, lasting = self.composition.switched()
        if not (self.composition.hints or lasting):
            return
        if screen().shell:  # the mode switch briefly at the caret, or the held exchange's pill
            screen().publish(self.drawn, "", spec, lasting=lasting)
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

    def do_candidate_clicked(self, index, button, state):
        """A click on a row of IBus's popup: taken as Tab would take it (as on macOS)."""
        action = self.composition.click(index)
        if action == "choose":  # a question's choice: answered
            chosen = self.composition.answer_choice()
            if chosen:
                self.suggestions.answer(*chosen)
            self.render()
        elif action == "accept":  # a draft: inserted
            self.finish(True)

    def resume(self):
        """Focus in: the poll timer again (it stops while another box has focus), and what came meanwhile."""
        self.focused = True
        screen().on_presence = self.render
        if self.timer is None:
            self.timer = GLib.timeout_add(40, self.poll)
            self.poll()

    def do_focus_in_id(self, object_path, client):
        # IBus 1.5.27+: client is "<im module>:<program>", for example "gtk3-im:firefox".
        self.app = None if client in ("", "fake") else client.split(":", 1)[-1]
        trace("focus-in", client)
        self.shared = client == "gnome-shell" and object_path  # every app's context (GNOME on Wayland)
        if self.shared:
            screen().on_focus = self.window_changed
            if screen().focus:  # the window the extension says has focus: the box and its app
                app, window = screen().focus
                self.app, object_path = app or self.app, "%s#%s" % (object_path, window)
        # One conversation per text box (its input context), as on Windows: earlier instructions,
        # context and approvals stay with the box they were made in, also when you come back to it.
        self.suggestions.use_conversation(object_path)
        self.context = object_path
        self.resume()
        self.update_quiet()
        self.refresh_surrounding()
        self.show_mode(register=True)
        pill = self.composition.returned(self.context)  # back in the box where an exchange was held: a pill, no keys
        if pill and screen().shell:
            screen().publish(None, "", pill, lasting=True)

    def window_changed(self, same=False):
        """GNOME on Wayland: another window has focus in the one input context every app shares.
        An exchange out is held for the window it was in; typed words are IBus's to commit. same:
        the window you are in, named again (its class set late): only its app is taken up."""
        if not (self.shared and self.focused):
            return
        self.shift.cancel()  # another window took focus (a Shift+click): its Shift is not a tap
        if not same:
            self.hold()
        self.do_focus_in_id(self.shared, "gnome-shell")

    def do_focus_in(self):
        """An IBus without focus ids (before 1.5.27): this engine's input context is the text box."""
        if self.own_path:
            self.do_focus_in_id(self.own_path, "")

    def do_focus_out(self):
        trace("focus-out")
        self.focused = False
        self.shift.cancel()  # focus moved (a Shift+click): its Shift is not a tap
        if screen().on_presence == self.render:
            screen().on_presence = None
        self.sequence = None  # a Compose key waiting goes with the focus
        if self.timer is not None:  # another box's engine polls now; results wait in the worker
            GLib.source_remove(self.timer)
            self.timer = None
        if screen().shell:
            screen().end_toast()  # a pill (held exchange) belongs to the box it was shown at, which is left
        if self.hold():
            return
        # IBus commits the visible preedit (words you were typing) through PreeditFocusMode.COMMIT.
        self.do_reset()

    def hold(self):
        """An instruction's exchange is held for this text box, its work going on. True when held."""
        if not self.composition.for_model:
            return False
        self.composition.leave(self.context)
        self.render()
        return True

    def do_disable(self):
        self.finish()

    def refresh_surrounding(self):
        """Ask the client for fresh surrounding text now: asking only when a key arrives returns stale text."""
        self.surrounding()

    def do_reset(self):
        self.sequence = None
        self.shift.cancel()  # a click (Shift+click): its Shift is not a tap
        trace("reset")
        if self.hold():  # a click in the field: the exchange is held, as on a focus change
            return
        self.composition.change("")
        self.changed()
        self.refresh_surrounding()

    def do_destroy(self):
        if self.focused:  # another box's engine may be the one drawing now (X11: one engine per box)
            screen().publish()  # nothing at the caret
        if self.timer is not None:
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
        path = "/org/freedesktop/IBus/Engine/Claudish/%d" % next(engines)
        try:  # has_focus_id makes IBus (1.5.27+) report which program has focus (do_focus_in_id)
            return ClaudishEngine(engine_name=name, connection=bus.get_connection(), has_focus_id=True, object_path=path)
        except TypeError:  # an older IBus (Ubuntu 22.04's 1.5.26): plain focus-in, an engine per input context
            engine = ClaudishEngine(engine_name=name, connection=bus.get_connection(), object_path=path)
            engine.own_path = path
            return engine

    factory.connect("create-engine", create)
    bus.request_name("org.freedesktop.IBus.Claudish", 0)
    bus.connect("disconnected", lambda *_: IBus.quit())
    IBus.main()


if __name__ == "__main__":
    main()
