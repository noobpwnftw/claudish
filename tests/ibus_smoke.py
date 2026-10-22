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
    engine.composition.mode = "rewrite"  # the rest exercises rewrite
    engine.composition.change("")
    for char in "hello-world":
        assert engine.do_process_key_event(ord(char), 0, 0)
    assert engine.composition.text == "hello—world"
    assert not engine.do_process_key_event(IBus.KEY_Shift_L, 0, 0)
    assert engine.composition.text == "hello—world"
    # AltGr, Num Lock, and similar keys alone must not end the phrase.
    for keyval in (IBus.KEY_ISO_Level3_Shift, IBus.KEY_Num_Lock, IBus.KEY_Meta_L, IBus.KEY_Hyper_L):
        assert not engine.do_process_key_event(keyval, 0, 0)
    assert engine.do_process_key_event(IBus.KEY_EuroSign, 0, IBus.ModifierType.MOD5_MASK)
    assert engine.composition.text == "hello—world€" and not commits
    engine.do_process_key_event(IBus.KEY_BackSpace, 0, 0)
    assert engine.do_process_key_event(IBus.KEY_Return, 0, 0)
    assert commits == ["hello—world"]
    for char in "draft":
        engine.do_process_key_event(ord(char), 0, 0)
    engine.composition.offer(engine.composition.revision, "A considered draft.")
    engine.do_process_key_event(IBus.KEY_Tab, 0, 0)
    assert commits[-1] == "A considered draft."
    for char in "say hi":
        engine.do_process_key_event(ord(char), 0, 0)
    engine.composition.offer(engine.composition.revision, "A rewrite.")
    assert engine.do_process_key_event(IBus.KEY_F7, 0, 0)
    # Continue types into the app: the held words go in and stay as the model's context.
    assert engine.composition.mode == "continue" and not engine.composition.candidate
    assert commits[-1] == "say hi" and engine.composition.text == "say hi"
    assert engine.do_process_key_event(ord("!"), 0, 0) and commits[-1] == "!"
    assert not engine.do_process_key_event(IBus.KEY_Tab, 0, 0)  # no suggestion: Tab is the app's
    engine.composition.offer(engine.composition.revision, "say hi! Hello—truly.")
    assert engine.composition.ghost == " Hello—truly."
    assert engine.do_process_key_event(IBus.KEY_Tab, 0, 0) and commits[-1] == " Hello—truly."
    engine.composition.offer(engine.composition.revision, "say hi! Hello—truly. Bye.")
    assert engine.do_process_key_event(IBus.KEY_Escape, 0, 0) and not engine.composition.ghost
    assert not engine.do_process_key_event(IBus.KEY_BackSpace, 0, 0)  # the app deletes; the context follows
    assert engine.composition.text == "say hi! Hello—truly"
    # A fresh start in continue (after a click or a paste) begins from the app's text before the caret.
    engine.composition.change("")
    engine.before_caret = lambda: "Pasted words. "
    assert engine.do_process_key_event(ord("W"), 0, 0)
    assert engine.composition.text == "Pasted words. W", engine.composition.text
    del engine.before_caret
    assert engine.do_process_key_event(IBus.KEY_F7, 0, 0) and engine.composition.mode == "instruct"
    assert engine.composition.text == ""  # the words are in the app already
    # Instruct holds the text; Enter sends it, and the next Enter inserts the result.
    for char in "story":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.composition.mode == "instruct" and not engine.composition.working
    assert engine.do_process_key_event(IBus.KEY_F8, 0, 0) and engine.composition.look
    assert engine.do_process_key_event(IBus.KEY_F8, 0, 0) and not engine.composition.look
    assert engine.do_process_key_event(IBus.KEY_Return, 0, 0)
    assert engine.composition.working and engine.composition.text == "story"
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
    engine.do_set_content_type(IBus.InputPurpose.PASSWORD, 0)
    assert not engine.do_process_key_event(ord("x"), 0, 0)
    assert not engine.composition.text
    print("IBus binding smoke passed: continue by default, composition, modifiers, commit, candidate, modes, live continue, F8, candidate list, password bypass")
finally:
    engine.destroy()
