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
claudish.composition.ENTER_GUARD_SECONDS = 0  # Enter right after a result; the guard has its own test
IBus.init()
connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
engine = module.ClaudishEngine(connection=connection, object_path="/org/claudish/TestEngine")
commits = []
engine.commit_text = lambda text: commits.append(text.get_text())
try:
    # Switching to cd_AI types like en_US: continue, keys straight in, hyphens kept.
    assert engine.composition.mode == "continue"
    for char in "ls -la":
        assert engine.do_process_key_event(ord(char), 0, 0)
    assert "".join(commits) == "ls -la", commits
    assert not engine.do_process_key_event(IBus.KEY_Tab, 0, 0)  # nothing offered: Tab is the app's
    commits.clear()

    def shift_tap():
        assert not engine.do_process_key_event(IBus.KEY_Shift_L, 0, 0)
        assert not engine.do_process_key_event(IBus.KEY_Shift_L, 0, IBus.ModifierType.RELEASE_MASK)

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
    assert engine.composition.working and engine.composition.request_mode == "rewrite"
    engine.composition.offer(engine.composition.revision, "A considered draft.")  # in place as it arrives
    assert engine.composition.shown == "A considered draft." and commits[-1] == "hello-world"
    engine.do_process_key_event(IBus.KEY_Tab, 0, 0)  # Tab again keeps it
    assert commits[-1] == "A considered draft."
    # Continue types into the app; the context follows; Tab takes a suggestion.
    shift_tap()
    assert engine.composition.mode == "continue"
    assert engine.do_process_key_event(ord("!"), 0, 0) and commits[-1] == "!"
    assert not engine.do_process_key_event(IBus.KEY_Tab, 0, 0)  # no suggestion: Tab is the app's
    engine.composition.offer(engine.composition.revision, engine.composition.text + " Hello—truly.")
    assert engine.composition.ghost == " Hello—truly."
    assert engine.do_process_key_event(IBus.KEY_Tab, 0, 0) and commits[-1] == " Hello—truly."
    engine.composition.offer(engine.composition.revision, engine.composition.text + " Bye.")
    assert engine.do_process_key_event(IBus.KEY_Escape, 0, 0) and not engine.composition.ghost
    assert not engine.do_process_key_event(IBus.KEY_BackSpace, 0, 0)  # the app deletes; the context follows
    # A fresh start in continue (after a click or a paste) begins from the app's text before the caret.
    engine.composition.change("")
    engine.before_caret = lambda: "Pasted words. "
    assert engine.do_process_key_event(ord("W"), 0, 0)
    assert engine.composition.text == "Pasted words. W", engine.composition.text
    del engine.before_caret
    assert engine.do_process_key_event(IBus.KEY_F7, 0, 0) is False  # F7 is the app's now
    shift_tap()
    assert engine.composition.mode == "compose" and engine.composition.text == ""  # the words are in the app
    # Compose holds the text; Enter sends it as an instruction, and the next Enter inserts the result.
    for char in "story":
        engine.do_process_key_event(ord(char), 0, 0)
    assert not engine.composition.working
    assert engine.do_process_key_event(IBus.KEY_F8, 0, 0) and engine.composition.look
    assert engine.do_process_key_event(IBus.KEY_F8, 0, 0) and not engine.composition.look
    assert engine.do_process_key_event(IBus.KEY_Return, 0, 0)
    assert engine.composition.working and engine.composition.request_mode == "instruct"
    engine.composition.offer(engine.composition.revision, "Once upon a time—a cat.")
    assert engine.do_process_key_event(IBus.KEY_Return, 0, 0)
    assert commits[-1] == "Once upon a time—a cat."
    # Several readings of an instruction: a numbered list; 2 inserts the second.
    for char in "greet":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Return, 0, 0)
    engine.composition.offer(engine.composition.revision, "Hello.", ["Hi there.", "Greetings."])
    assert engine.composition.choosing
    engine.render()
    assert engine.do_process_key_event(IBus.KEY_2, 0, 0)
    assert commits[-1] == "Hi there." and not engine.composition.text
    # Shift+Enter keeps your words as they are, and stays in compose.
    for char in "as is":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Return, 0, IBus.ModifierType.SHIFT_MASK)
    assert commits[-1] == "as is" and engine.composition.mode == "compose" and not engine.composition.text
    assert not engine.do_process_key_event(IBus.KEY_Return, 0, IBus.ModifierType.SHIFT_MASK)  # nothing composed
    # Esc with just your words drops them (Shift+Enter keeps them).
    for char in "nope":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Escape, 0, 0) and not engine.composition.text
    assert commits[-1] == "as is"  # nothing new was inserted
    # The indicator's menu picks a mode, as a Shift tap does.
    engine.do_property_activate("mode.continue", IBus.PropState.CHECKED)
    assert engine.composition.mode == "continue"
    engine.do_property_activate("mode.compose", IBus.PropState.UNCHECKED)  # a radio item turning off: nothing
    assert engine.composition.mode == "continue"
    # A terminal (its field purpose, or the program) is not prose: continue asks nothing there.
    engine.do_set_content_type(IBus.InputPurpose.TERMINAL, 0)
    assert engine.composition.quiet and not engine.composition.automatic
    engine.do_set_content_type(IBus.InputPurpose.FREE_FORM, 0)
    engine.do_focus_in_id("/", "gtk3-im:gnome-terminal-server")
    assert engine.composition.quiet
    engine.do_focus_in_id("/", "gtk3-im:gedit")
    assert not engine.composition.quiet
    engine.do_set_content_type(IBus.InputPurpose.PASSWORD, 0)
    assert not engine.do_process_key_event(ord("x"), 0, 0)
    assert not engine.composition.text
    print("IBus binding smoke passed: continue by default, composition, modifiers, commit, Shift tap, compose (rewrite on Tab, instruct on Enter), live continue, F8, candidate list, mode menu, quiet in terminals, password bypass")
finally:
    engine.destroy()
