"""Run: dbus-run-session -- /usr/bin/python3 tests/ibus_smoke.py

Exercises the real GObject/IBus bindings on an isolated session bus, without
registering the input method or touching desktop settings. Not an app UI test.
"""
import importlib.util
from pathlib import Path

import gi
gi.require_version("IBus", "1.0")
from gi.repository import Gio, IBus

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("claudish_ibus", root / "platforms/linux/engine.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
import claudish.composition
claudish.composition.ROLLED_SHIFT_SECONDS = 0  # a Shift right after a key; the filter has its own test
IBus.init()
connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
engine = module.ClaudishEngine(connection=connection, object_path="/org/claudish/TestEngine")
commits = []
engine.commit_text = lambda text: commits.append(text.get_text())
preedits = []  # (text, visible) as drawn
engine.update_preedit_text_with_mode = lambda text, cursor, visible, mode: preedits.append((text.get_text() if visible else "", visible))
try:
    def shift_tap():
        assert not engine.do_process_key_event(IBus.KEY_Shift_L, 0, 0)
        assert not engine.do_process_key_event(IBus.KEY_Shift_L, 0, IBus.ModifierType.RELEASE_MASK)

    assert engine.composition.mode == "compose"  # where cd_AI starts
    # A Shift tap goes to continue, which types like en_US: keys straight in, hyphens kept.
    shift_tap()
    assert engine.composition.mode == "continue"
    for char in "ls -la":  # passed on: the app inserts each key and reports its caret after it
        assert not engine.do_process_key_event(ord(char), 0, 0)
    assert engine.composition.text == "ls -la" and not commits, commits
    assert not engine.do_process_key_event(IBus.KEY_Tab, 0, 0)  # nothing offered: Tab is the app's
    # A dead key in continue: its accent waits at the caret, then goes on the letter.
    assert engine.do_process_key_event(IBus.keyval_from_name("dead_acute"), 0, 0)
    assert engine.composition.accent == "´"
    assert engine.focus_mode() == IBus.PreeditFocusMode.CLEAR  # the accent alone: not typed when focus goes
    assert engine.do_process_key_event(ord("e"), 0, 0) and commits == ["é"], commits
    assert engine.composition.text == "ls -laé" and not engine.composition.accent
    commits.clear()

    shift_tap()  # a Shift tap: compose, which holds what you type
    assert engine.composition.mode == "compose"
    for char in "hello-world":
        assert engine.do_process_key_event(ord(char), 0, 0)
    assert engine.composition.text == "hello-world"
    # Shift held for a capital is not a tap.
    engine.do_process_key_event(IBus.KEY_Shift_L, 0, 0)
    engine.do_process_key_event(ord("X"), 0, IBus.ModifierType.SHIFT_MASK)
    engine.do_process_key_event(IBus.KEY_Shift_L, 0, IBus.ModifierType.RELEASE_MASK)
    assert engine.composition.mode == "compose" and engine.composition.text == "hello-worldX"
    # Ctrl+Shift (a layout-switch chord) is not a tap.
    engine.do_process_key_event(IBus.KEY_Control_L, 0, 0)
    engine.shift.typed_at = 0  # Shift long after the Ctrl press: not rolled typing, only the chord counts
    engine.do_process_key_event(IBus.KEY_Shift_L, 0, IBus.ModifierType.CONTROL_MASK)
    engine.do_process_key_event(IBus.KEY_Shift_L, 0, IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.RELEASE_MASK)
    engine.do_process_key_event(IBus.KEY_Control_L, 0, IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.RELEASE_MASK)
    assert engine.composition.mode == "compose", "Ctrl+Shift switched modes"
    engine.do_process_key_event(IBus.KEY_BackSpace, 0, 0)
    # AltGr, Num Lock, and similar keys alone must not end the phrase.
    for keyval in (IBus.KEY_ISO_Level3_Shift, IBus.KEY_Num_Lock, IBus.KEY_Meta_L, IBus.KEY_Hyper_L):
        assert not engine.do_process_key_event(keyval, 0, 0)
    assert engine.do_process_key_event(IBus.KEY_EuroSign, 0, IBus.ModifierType.MOD5_MASK)
    assert engine.composition.text == "hello-world€" and not commits
    engine.do_process_key_event(IBus.KEY_BackSpace, 0, 0)
    shift_tap()  # Shift keeps your words as typed, and goes back to continue
    assert commits == ["hello-world"] and engine.composition.mode == "continue"
    assert engine.composition.text == "hello-world"  # in the app now: continue's context
    shift_tap()
    for char in "draft":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Tab, 0, 0)  # Tab asks for the rewrite
    assert engine.composition.working and engine.composition.asked == "rewrite"
    engine.composition.offer(engine.composition.revision, "A considered draft.")  # it arrives in the panel
    # Your words stay the preedit; the rewrite waits in the panel for Tab (IBus commits the preedit on
    # focus-out, so it must only ever hold your words).
    assert engine.composition.shown == "draft" and engine.composition.panel()["body"] == "A considered draft."
    assert commits[-1] == "hello-world"
    engine.do_process_key_event(IBus.KEY_Tab, 0, 0)  # Tab again keeps it
    assert commits[-1] == "A considered draft."
    # Continue types into the app; the context follows; Tab takes a suggestion.
    shift_tap()
    assert engine.composition.mode == "continue"
    assert not engine.do_process_key_event(ord("!"), 0, 0) and engine.composition.text.endswith("!")  # the app's
    assert not engine.do_process_key_event(IBus.KEY_Tab, 0, 0)  # no suggestion: Tab is the app's
    engine.composition.offer(engine.composition.revision, engine.composition.text + " Hello—truly.")
    assert engine.composition.ghost == " Hello—truly."
    assert engine.do_process_key_event(IBus.KEY_Tab, 0, 0) and commits[-1] == " Hello—truly."
    # A click elsewhere sends no key (a GTK 3 app resets nothing when keys went straight in): Tab
    # never takes a suggestion asked for another place.
    engine.composition.offer(engine.composition.revision, engine.composition.text + " Moved.")
    real = engine.around_caret
    engine.around_caret = lambda: ("Another paragraph", "")
    count = len(commits)
    assert not engine.do_process_key_event(IBus.KEY_Tab, 0, 0) and len(commits) == count
    assert not engine.composition.ghost
    engine.around_caret = lambda: ("Earlier text " + engine.composition.text, "")  # still there: taken
    engine.composition.offer(engine.composition.revision, engine.composition.text + " Here.")
    assert engine.do_process_key_event(IBus.KEY_Tab, 0, 0) and commits[-1] == " Here."
    engine.around_caret = real
    engine.composition.offer(engine.composition.revision, engine.composition.text + " Bye.")
    assert engine.do_process_key_event(IBus.KEY_Escape, 0, 0) and not engine.composition.ghost
    assert not engine.do_process_key_event(IBus.KEY_BackSpace, 0, 0)  # the app deletes; the context follows
    # A fresh start in continue (after a click or a paste) begins from the app's text before the caret.
    engine.composition.change("")
    engine.before_caret = lambda: "Pasted words. "
    assert not engine.do_process_key_event(ord("W"), 0, 0)
    assert engine.composition.text == "Pasted words. W", engine.composition.text
    del engine.before_caret
    shift_tap()
    assert engine.composition.mode == "compose" and engine.composition.text == ""  # the words are in the app
    # Compose holds the text; Shift+Enter sends it as an instruction; Enter then puts nothing in.
    for char in "story":
        engine.do_process_key_event(ord(char), 0, 0)
    assert not engine.composition.working
    assert engine.do_process_key_event(IBus.KEY_F8, 0, 0) and engine.composition.look
    assert engine.do_process_key_event(IBus.KEY_F8, 0, 0) and not engine.composition.look
    assert engine.do_process_key_event(IBus.KEY_Return, 0, IBus.ModifierType.SHIFT_MASK)
    assert engine.composition.working and engine.composition.asked == "instruct"
    engine.composition.offer(engine.composition.revision, "Once upon a time—a cat.")
    assert engine.do_process_key_event(IBus.KEY_Return, 0, 0) and commits[-1] != "Once upon a time—a cat."  # a reflexive Enter: nothing in
    assert engine.do_process_key_event(IBus.KEY_Tab, 0, 0)  # Tab takes the model's text
    assert commits[-1] == "Once upon a time—a cat."
    # Several readings of an instruction: a list (not numbered: digits are text); ↓ Tab inserts the second.
    for char in "greet":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Return, 0, IBus.ModifierType.SHIFT_MASK)
    engine.composition.offer(engine.composition.revision, "Hello.", ["Hi there.", "Greetings."])
    assert len(engine.composition.panel()["rows"]) > 1  # the drafts, as rows
    engine.render()
    assert engine.do_process_key_event(IBus.KEY_Down, 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Tab, 0, 0)
    assert commits[-1] == "Hi there." and not engine.composition.text
    # A click on a row takes it, as Tab would.
    for char in "greet":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Return, 0, IBus.ModifierType.SHIFT_MASK)
    engine.composition.offer(engine.composition.revision, "Hello.", ["Hi there.", "Greetings."])
    engine.do_candidate_clicked(2, 1, 0)
    assert commits[-1] == "Greetings." and not engine.composition.text
    # Enter keeps your words as they are (the app gets the next Enter), and stays in compose.
    for char in "as is":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Return, 0, 0)
    assert commits[-1] == "as is" and engine.composition.mode == "compose" and not engine.composition.text
    assert not engine.do_process_key_event(IBus.KEY_Return, 0, IBus.ModifierType.SHIFT_MASK)  # nothing composed: the app's
    # Esc with just your words drops them (Enter keeps them).
    for char in "nope":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Escape, 0, 0) and not engine.composition.text
    assert commits[-1] == "as is"  # nothing new was inserted
    # Dead keys compose in the composition: ´ then e is é; ´ then space is the accent.
    for char in "caf":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.keyval_from_name("dead_acute"), 0, 0)
    assert engine.do_process_key_event(ord("e"), 0, 0)
    assert engine.do_process_key_event(IBus.keyval_from_name("dead_circumflex"), 0, 0)
    assert engine.do_process_key_event(ord(" "), 0, 0)
    assert engine.composition.text == "café^", engine.composition.text
    assert engine.do_process_key_event(IBus.KEY_Escape, 0, 0) and not engine.composition.text
    # Delete with nothing composed is the app's (it typed a DEL character once).
    count = len(commits)
    assert not engine.do_process_key_event(IBus.KEY_Delete, 0, 0) and len(commits) == count
    # An accent waiting for its letter: Backspace cancels it, and only it.
    assert engine.do_process_key_event(IBus.keyval_from_name("dead_acute"), 0, 0)
    assert engine.do_process_key_event(IBus.KEY_BackSpace, 0, 0)
    engine.do_process_key_event(ord("e"), 0, 0)
    assert engine.composition.text == "e", engine.composition.text
    engine.do_process_key_event(IBus.KEY_Escape, 0, 0)
    # The Compose key: Compose ' e is é, in the composition, as a dead key's is.
    for char in "caf":
        engine.do_process_key_event(ord(char), 0, 0)
    for keyval in (IBus.keyval_from_name("Multi_key"), ord("'"), ord("e")):
        assert engine.do_process_key_event(keyval, 0, 0)
    assert engine.composition.text == "café", engine.composition.text
    engine.do_process_key_event(IBus.KEY_Escape, 0, 0)
    # Its whole table (the system's X11 one): Compose o c is ©, Compose - - - an em dash.
    for keys, made in ((("o", "c"), "©"), (("-", "-", "-"), "\u2014")):
        for char in "x":
            engine.do_process_key_event(ord(char), 0, 0)
        engine.do_process_key_event(IBus.keyval_from_name("Multi_key"), 0, 0)
        for key in keys:
            assert engine.do_process_key_event(ord(key), 0, 0)
        assert engine.composition.text == "x" + made, engine.composition.text
        engine.do_process_key_event(IBus.KEY_Escape, 0, 0)
    # Keys IBus names otherwise than the files: Compose ' ơ (U+01A1, ohorn in the table) is ớ.
    engine.do_process_key_event(IBus.keyval_from_name("Multi_key"), 0, 0)
    engine.do_process_key_event(ord("'"), 0, 0)
    assert engine.do_process_key_event(0x10001A1, 0, 0)
    assert engine.composition.text == "\u1edb", engine.composition.text
    engine.do_process_key_event(IBus.KEY_Escape, 0, 0)
    # A dead key beyond the accents drawn here (Vietnamese's dot below, hook): the compose table's
    # sequence, in the composition; the word goes on.
    for char in "Vi":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.keyval_from_name("dead_belowdot"), 0, 0)
    assert engine.do_process_key_event(ord("e"), 0, 0)
    assert engine.do_process_key_event(IBus.keyval_from_name("dead_hook"), 0, 0)
    assert engine.do_process_key_event(ord("e"), 0, 0)
    assert engine.composition.text == "Vi\u1eb9\u1ebb", engine.composition.text
    engine.do_process_key_event(IBus.KEY_Escape, 0, 0)
    # The dead tilde (dead_perispomeni to IBus): ñ.
    engine.do_process_key_event(IBus.keyval_from_name("dead_tilde"), 0, 0)
    engine.do_process_key_event(ord("n"), 0, 0)
    assert engine.composition.text == "\u00f1", engine.composition.text
    engine.do_process_key_event(IBus.KEY_Escape, 0, 0)
    # Backspace takes back the Compose key (as GTK's), and deletes nothing.
    for char in "don":
        engine.do_process_key_event(ord(char), 0, 0)
    engine.do_process_key_event(IBus.keyval_from_name("Multi_key"), 0, 0)
    engine.do_process_key_event(IBus.KEY_BackSpace, 0, 0)
    for char in "'t":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.composition.text == "don't", engine.composition.text
    engine.do_process_key_event(IBus.KEY_Escape, 0, 0)
    engine.do_process_key_event(IBus.keyval_from_name("Multi_key"), 0, 0)
    engine.do_reset()  # a click: the Compose key's wait ends with it
    engine.do_process_key_event(ord("'"), 0, 0)
    assert "´" not in engine.composition.drawn, engine.composition.drawn
    engine.do_process_key_event(IBus.KEY_Escape, 0, 0)
    # An accent left waiting goes with the composition (a reset: a click, a focus change), not onto
    # the next letter.
    assert engine.do_process_key_event(IBus.keyval_from_name("dead_acute"), 0, 0)
    assert engine.focus_mode() == IBus.PreeditFocusMode.CLEAR  # alone, it is not committed when focus goes
    engine.do_reset()
    engine.do_process_key_event(ord("e"), 0, 0)
    assert engine.composition.text == "e", engine.composition.text
    engine.do_process_key_event(IBus.KEY_Escape, 0, 0)
    # The accent and punctuation with nothing composed go to the app, as the punctuation alone would.
    count = len(commits)
    assert engine.do_process_key_event(IBus.keyval_from_name("dead_acute"), 0, 0)
    assert engine.do_process_key_event(ord(","), 0, 0)
    assert commits[count:] == ["´,"] and not engine.composition.text, (commits[count:], engine.composition.text)
    assert not preedits[-1][0], preedits[-1]  # not left drawn (a focus change would type it again)
    # Shift+Esc while composing brings nothing back, and drops nothing.
    for char in "keep me":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Escape, 0, IBus.ModifierType.SHIFT_MASK)
    assert engine.composition.text == "keep me"
    engine.do_process_key_event(IBus.KEY_Escape, 0, 0)
    # A shortcut while an instruction is out: the instruction is cleared, held with its exchange for Shift+Esc.
    for char in "fix it":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Return, 0, IBus.ModifierType.SHIFT_MASK) and engine.composition.sent
    assert not engine.do_process_key_event(ord("a"), 0, IBus.ModifierType.CONTROL_MASK)
    assert commits[-1] != "fix it" and engine.composition.held is not None and not engine.composition.text  # held, not typed in
    # Shift+Esc brings it back without asking again: its request is still running.
    # (Counted at schedule: the worker's thread takes pending requests at any moment.)
    scheduled, schedule = [], engine.suggestions.schedule
    engine.suggestions.schedule = lambda *args, **kwargs: (scheduled.append(args), schedule(*args, **kwargs))
    assert engine.do_process_key_event(IBus.KEY_Escape, 0, IBus.ModifierType.SHIFT_MASK)
    assert engine.composition.text == "fix it" and scheduled == [], scheduled
    engine.suggestions.schedule = schedule
    engine.do_reset()
    engine.composition.held = None
    # One conversation per text box: a new input context starts a fresh one.
    engine.do_focus_in_id("/org/freedesktop/IBus/InputContext_7", "gtk3-im:gedit")
    first = engine.suggestions.conversation
    engine.do_focus_in_id("/org/freedesktop/IBus/InputContext_7", "gtk3-im:gedit")
    assert engine.suggestions.conversation == first  # the same box again
    engine.do_focus_in_id("/org/freedesktop/IBus/InputContext_8", "gtk3-im:firefox")
    assert engine.suggestions.conversation != first
    # The indicator's menu picks a mode, as a Shift tap does.
    engine.do_property_activate("mode.continue", IBus.PropState.CHECKED)
    assert engine.composition.mode == "continue"
    engine.do_property_activate("mode.compose", IBus.PropState.UNCHECKED)  # a radio item turning off: nothing
    assert engine.composition.mode == "continue"
    # Settings… beside the modes: the page in the browser, off the main loop.
    opened = []
    module.open_settings, real_open = (lambda: opened.append(True)), module.open_settings
    engine.do_property_activate("settings", IBus.PropState.UNCHECKED)
    module.open_settings = real_open
    assert opened == [True] and engine.composition.mode == "continue"
    # A terminal (its field purpose, or the program) is not prose: continue asks nothing there.
    engine.do_set_content_type(IBus.InputPurpose.TERMINAL, 0)
    assert engine.composition.quiet and not engine.composition.automatic
    engine.do_set_content_type(IBus.InputPurpose.FREE_FORM, 0)
    engine.do_focus_in_id("/", "gtk3-im:gnome-terminal-server")
    assert engine.composition.quiet
    engine.do_focus_in_id("/", "gtk3-im:gedit")
    assert not engine.composition.quiet
    shift_tap()  # compose: what you type is held
    assert engine.composition.mode == "compose"
    for char in "hunter":
        engine.do_process_key_event(ord(char), 0, 0)
    engine.do_set_content_type(IBus.InputPurpose.PASSWORD, 0)  # the field became a password field
    assert commits[-1] == "hunter" and not engine.composition.text, commits[-1:]  # typed words went in
    assert not engine.do_process_key_event(ord("x"), 0, 0)
    assert not engine.composition.text
    # The GNOME extension appears or goes (enabled, disabled, the shell restarted): the focused box
    # draws again where its panel now is; a box without focus does not.
    engine.resume()
    shown = module.screen()
    for present in (True, False):
        before = len(preedits)
        shown.watch(present)
        assert len(preedits) > before and shown.shell is present, (present, preedits[before:])
        before = len(preedits)
        shown.watch(present)  # no change: nothing to draw
        assert len(preedits) == before
    engine.do_focus_out()
    before = len(preedits)
    shown.watch(True)
    assert len(preedits) == before and shown.on_presence is None
    shown.watch(False)
    print("IBus binding smoke passed: compose by default, composition, modifiers, commit, Shift tap, compose (rewrite on Tab, instruct on Shift+Enter, keep on Enter), live continue, F8, candidate list, row clicks, Delete, dead keys, Shift+Esc, mode menu, quiet in terminals, password bypass")
finally:
    engine.destroy()
