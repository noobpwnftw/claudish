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
    assert engine.composition.mode == "continue" and not engine.composition.candidate
    engine.do_process_key_event(IBus.KEY_F7, 0, 0)
    engine.composition.offer(engine.composition.revision, "Hello—truly.")
    engine.do_process_key_event(IBus.KEY_Tab, 0, 0)
    assert commits[-1] == "Hello—truly." and engine.composition.mode == "instruct"
    # Instruct holds the text; Enter sends it, and the next Enter inserts the result.
    for char in "story":
        engine.do_process_key_event(ord(char), 0, 0)
    assert engine.composition.mode == "instruct" and not engine.composition.working
    assert engine.do_process_key_event(IBus.KEY_Return, 0, 0)
    assert engine.composition.working and engine.composition.text == "story"
    engine.composition.offer(engine.composition.revision, "Once upon a time—a cat.")
    assert engine.do_process_key_event(IBus.KEY_Return, 0, 0)
    assert commits[-1] == "Once upon a time—a cat."
    engine.do_set_content_type(IBus.InputPurpose.PASSWORD, 0)
    assert not engine.do_process_key_event(ord("x"), 0, 0)
    assert not engine.composition.text
    print("IBus binding smoke passed: composition, modifiers, commit, candidate, modes, password bypass")
finally:
    engine.destroy()
