"""Exercise the Windows adapter against PIME's actual Python API, on either OS.

python tests/pime_smoke.py --pime-source /path/to/PIME/python/textService.py
This does not register or exercise the native TSF component.
"""
import argparse
import json
import os
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pime-source", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("textService", args.pime_source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["textService"] = module
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "pime_claudish"
        shutil.copytree(root / "platforms/windows/claudish", target)
        for name in ["composition.py", "client.py", "screen.py"]:
            shutil.copy(root / "claudish" / name, target / name)
        sys.path.insert(0, temporary)
        from pime_claudish.claudish_ime import ClaudishTextService
        with patch("pime_claudish.claudish_ime.Suggestions") as worker_class:
            worker_class.return_value.poll.return_value = None
            service = ClaudishTextService(None)
            reply = service.handleRequest({"method": "onActivate", "isKeyboardOpen": True})
            # The mode in the taskbar's input indicator; its menu and a click switch it.
            button = [b for b in reply["addButton"] if b["id"] == "windows-mode-icon"][0]
            assert button["icon"].endswith("mode-continue.ico") and os.path.exists(button["icon"]), button
            reply = service.handleRequest({"method": "onCommand", "id": 100, "type": 0})
            assert service.state.mode == "compose" and reply["changeButton"][0]["icon"].endswith("mode-compose.ico"), reply
            menu = service.handleRequest({"method": "onMenu", "id": "windows-mode-icon"})["return"]
            assert [(m["text"], m["checked"]) for m in menu] == [("continue", False), ("compose", True)], menu
            service.handleRequest({"method": "onCommand", "id": menu[0]["id"], "type": 0})
            assert service.state.mode == "continue"

            def key(code, char=0, method="onKeyDown", modifiers=(), **around):
                states = [0] * 256
                for modifier in modifiers:
                    states[modifier] = 128
                return service.handleRequest(dict({"method": method, "seqNum": 1,
                    "charCode": char, "keyCode": code, "repeatCount": 1,
                    "scanCode": 0, "isExtended": False, "keyStates": states}, **around))

            def shift_tap():
                """Shift pressed and released alone: its key-up is taken, and onKeyUp switches mode."""
                assert key(0x10, method="filterKeyDown")["return"] is False  # the app sees Shift too
                assert key(0x10, method="filterKeyUp")["return"] is True
                assert key(0x10, method="filterKeyUp")["return"] is True  # PIME asks twice; the same answer
                return key(0x10, method="onKeyUp")

            # Switching to cd_AI types like en_US: continue, keys straight in, hyphens kept.
            assert service.state.mode == "continue"
            typed = "".join(key(ord(c.upper()), ord(c)).get("commitString", "") for c in "ls -la")
            assert typed == "ls -la", typed
            assert key(9, method="filterKeyDown")["return"] is False  # nothing offered: Tab is the app's
            shift_tap()  # compose: what you type is held
            assert service.state.mode == "compose"
            for char in "hello-world":
                assert key(ord(char.upper()), ord(char), "filterKeyDown")["return"]
                reply = key(ord(char.upper()), ord(char))
            assert reply["compositionString"] == "hello—world"
            # A modifier and a shortcut must not consume or rewrite composition.
            assert not key(0x10, method="filterKeyDown")["return"]
            # Ctrl/Alt shortcuts mid-composition: commit the wording first, then pass the key on.
            assert key(ord("C"), method="filterKeyDown", modifiers=(0x11,))["return"]
            reply = key(ord("C"), modifiers=(0x11,))
            assert reply["commitString"] == "hello—world" and reply["return"], reply  # committed, key consumed
            for char in "hello-world":
                key(ord(char.upper()), ord(char))
            assert key(ord("C"), method="filterKeyDown", modifiers=(0x11, 0x12))["return"] is True
            assert service.state.text == "hello—world"
            # AltGr arrives as Ctrl+Alt; a printable result belongs in the phrase.
            assert key(ord("Q"), ord("@"), "filterKeyDown", modifiers=(0x11, 0x12))["return"]
            assert key(ord("Q"), ord("@"), modifiers=(0x11, 0x12))["compositionString"] == "hello—world@"
            key(0x08)
            assert service.state.text == "hello—world"
            # Tab asks for the rewrite and commits nothing; a Shift tap keeps your words as typed.
            assert "commitString" not in key(9)
            reply = shift_tap()
            assert reply["commitString"] == "hello—world" and service.state.mode == "continue", reply
            assert key(0x10, method="filterKeyDown")["return"] is False  # Shift held for a capital: no tap
            key(ord("A"), ord("A"), "filterKeyDown")  # every key reaches filterKeyDown first
            key(ord("A"), ord("A"))
            assert key(0x10, method="filterKeyUp")["return"] is False and service.state.mode == "continue"
            shift_tap()
            for char in "draft":
                key(ord(char.upper()), ord(char))
            assert "commitString" not in key(9)  # Tab asks
            worker_class.return_value.poll.return_value = (service.state.revision, {"text": "A nuanced draft."})
            reply = key(0x75)  # it arrives: in place of your words, no list
            worker_class.return_value.poll.return_value = None
            assert reply["candidateList"] == [] and reply["compositionString"] == "A nuanced draft.", reply
            reply = key(0x1B)  # Esc: your words again
            assert "commitString" not in reply and reply["compositionString"] == "draft", reply
            key(9)  # the rewrite again, without asking again
            assert key(9)["commitString"] == "A nuanced draft."  # Tab again keeps it
            for char in "say hi":
                key(ord(char.upper()), ord(char))
            reply = shift_tap()
            assert service.state.mode == "continue" and "continue" in json.dumps(reply.get("showMessage")), reply
            assert reply["commitString"] == "say hi"  # Shift keeps your words; continue types into the app
            last = worker_class.return_value.schedule.call_args.args
            assert len(last) < 3 or last[2] != "continue"  # mid-word: no suggestion yet
            assert key(ord("!"), ord("!"))["commitString"] == "!"
            assert worker_class.return_value.schedule.call_args.args[2] == "continue"  # a word boundary asks
            assert key(9, method="filterKeyDown")["return"] is False  # no suggestion: Tab is the app's
            # The suggestion shows when the key is released: continue takes printable key-ups too.
            assert key(ord("!"), ord("!"), "filterKeyUp")["return"] is True
            worker_class.return_value.poll.return_value = (service.state.revision, {"text": "say hi! Hello—truly."})
            reply = key(ord("!"), ord("!"), "onKeyUp")
            assert reply.get("candidateList") == ["Tab: …Hello—truly."] and reply.get("showCandidates"), reply
            assert key(9, method="filterKeyUp")["return"] is False  # not a printable key: the app's
            assert key(9, method="filterKeyDown")["return"] is True  # a waiting suggestion makes Tab ours
            worker_class.return_value.poll.return_value = None
            assert key(9)["commitString"] == " Hello—truly."
            assert key(0x76, method="filterKeyDown")["return"] is False  # F7 is the app's now
            shift_tap()  # compose, starting empty: the words are in the app already
            for char in "as is":
                key(ord(char.upper()), ord(char))
            assert key(0x0D, modifiers=(0x10,))["commitString"] == "as is"  # Shift+Enter keeps it as it is
            assert service.state.mode == "compose" and service.state.text == ""
            assert service.state.mode == "compose" and service.state.text == ""
            # Compose: no request while typing; Enter sends it as an instruction; the next Enter inserts.
            calls = worker_class.return_value.schedule.call_count
            for char in "story":
                key(ord(char.upper()), ord(char))
            assert worker_class.return_value.schedule.call_count == calls
            reply = key(0x77)  # F8: send a picture of the window too
            assert service.state.look and "picture" in json.dumps(reply.get("showMessage")), reply
            reply = key(0x0D)
            assert service.state.working and "working" in json.dumps(reply.get("showMessage"))
            assert worker_class.return_value.schedule.call_args.kwargs["immediate"] is True
            assert worker_class.return_value.schedule.call_args.kwargs["look"] is True
            assert "commitString" not in key(0x0D)  # still working
            worker_class.return_value.poll.return_value = (service.state.revision, {"text": "Once upon a time."})
            assert key(0x0D)["commitString"] == "Once upon a time."
            worker_class.return_value.poll.return_value = None
            # Several readings: the candidate window lists them; 2 inserts the second.
            for char in "greet":
                key(ord(char.upper()), ord(char))
            key(0x0D)
            worker_class.return_value.poll.return_value = (service.state.revision,
                                                           {"text": "Hello.", "candidates": ["Hello.", "Hi there."]})
            reply = key(0x10)  # Shift: a key that only polls and publishes
            assert reply.get("candidateList") == ["Hello.", "Hi there."], reply
            worker_class.return_value.poll.return_value = None
            assert key(0x32)["commitString"] == "Hi there."
            # An agent session asks a question: the choices are the list, and a digit answers.
            for char in "check":
                key(ord(char.upper()), ord(char))
            key(0x0D)
            question = {"id": "perm-1", "text": "Allow Bash?",
                        "choices": [{"label": "Allow", "legend": "Bash: git status"}, {"label": "Deny"}]}
            worker_class.return_value.poll.return_value = (service.state.revision, {"question": question, "session": "s1"})
            reply = key(0x10)
            assert reply.get("candidateList") == ["Allow - Bash: git status", "Deny"], reply
            assert "Allow Bash?" in json.dumps(reply.get("showMessage")), reply
            worker_class.return_value.poll.return_value = None
            reply = key(0x31)
            assert "commitString" not in reply, reply
            assert worker_class.return_value.answer.call_args.args == ("s1", "perm-1", 0)
            # Another question: typed words answer it instead of a number.
            worker_class.return_value.poll.return_value = (service.state.revision, {"question": dict(question, id="perm-2"), "session": "s1"})
            key(0x10)
            worker_class.return_value.poll.return_value = None
            for char in "no 2":
                key(ord(char.upper()) if char.isalpha() else ord(char), ord(char))
            assert service.state.reply == "no 2" and not worker_class.return_value.answer.call_args.kwargs
            key(0x0D)
            assert worker_class.return_value.answer.call_args.kwargs == {"text": "no 2"}, worker_class.return_value.answer.call_args
            # Esc stops the session and goes back to the instruction; Esc again drops it unsent.
            reply = key(0x1B)
            assert "commitString" not in reply and service.state.text == "check", reply
            assert worker_class.return_value.schedule.call_args.args[1] == ""  # the pending answer is stopped
            assert key(0x1B)["commitString"] == ""  # nothing is inserted
            assert service.state.text == ""  # nothing composed: shortcuts are not taken at all
            assert key(ord("C"), method="filterKeyDown", modifiers=(0x11,))["return"] is False
            service.handleRequest({"method": "onKeyboardStatusChanged", "opened": False})
            assert not key(ord("X"), ord("x"), "filterKeyDown")["return"]
            if hasattr(service, "setTimer"):  # Claudish's PIME (platforms/windows/pime)
                # Requests carry the text around the caret, and an answer shows when it arrives.
                service.state.mode = "compose"
                service.handleRequest({"method": "onKeyboardStatusChanged", "opened": True})
                for char in "thanks":
                    key(ord(char.upper()), ord(char))
                reply = key(9, textBefore="Dear Ana, ", textAfter=" Best, Sam")
                kwargs = worker_class.return_value.schedule.call_args.kwargs
                assert (kwargs["before"], kwargs["after"], reply.get("timer")) == ("Dear Ana, ", " Best, Sam", 100), (kwargs, reply)
                reply = service.handleRequest({"method": "onTimer", "seqNum": 2})
                assert reply.get("timer") == 100  # still on its way: called back again
                worker_class.return_value.poll.return_value = (service.state.revision, {"text": "Thank you so much."})
                reply = service.handleRequest({"method": "onTimer", "seqNum": 3})
                worker_class.return_value.poll.return_value = None
                assert reply.get("compositionString") == "Thank you so much." and "timer" not in reply, reply
                key(9)  # keep it
                # An email field (IS_EMAIL_SMTPEMAILADDRESS) is not prose: nothing unasked, and named.
                service.state.mode = "continue"
                service.state.change("")
                key(ord("A"), ord("a"), inputScopes=[5])
                calls = len(worker_class.return_value.schedule.call_args_list)
                key(0x20, ord(" "), inputScopes=[5])
                assert all(len(c.args) < 3 or c.args[2] != "continue"
                           for c in worker_class.return_value.schedule.call_args_list[calls:])
                # One conversation per text box: another TSF context starts a new one.
                key(0x10, document="1")
                first = worker_class.return_value.new_conversation.call_count
                key(0x10, document="2")
                assert worker_class.return_value.new_conversation.call_count == first + 1
                # A password field (IS_PASSWORD): the first key is typed as is, then cd_AI stays out.
                service.state.change("")
                reply = key(ord("S"), ord("s"), inputScopes=[31])
                assert reply.get("commitString") == "s", reply
                assert key(ord("E"), ord("e"), method="filterKeyDown")["return"] is False
                print("patched PIME: text around the caret, answers on a timer, input scopes, one conversation per field, password fields")
            service.handleRequest({"method": "onDeactivate"})
            worker_class.return_value.close.assert_called_once()
        sys.path.remove(temporary)
    print("PIME Python contract smoke passed, continue by default, live continue, F8, candidate lists, and agent questions included (native TSF typing: tests/desktop/windows)")


if __name__ == "__main__":
    main()
