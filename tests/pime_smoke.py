"""Exercise the Windows adapter against PIME's actual Python API, on either OS.

python tests/pime_smoke.py --pime-source /path/to/PIME/python/textService.py
This does not register or exercise the native TSF component.
"""
import argparse
import json
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
        for name in ["composition.py", "client.py"]:
            shutil.copy(root / "claudish" / name, target / name)
        sys.path.insert(0, temporary)
        from pime_claudish.claudish_ime import ClaudishTextService
        with patch("pime_claudish.claudish_ime.Suggestions") as worker_class:
            worker_class.return_value.poll.return_value = None
            service = ClaudishTextService(None)
            service.handleRequest({"method": "onActivate", "isKeyboardOpen": True})

            def key(code, char=0, method="onKeyDown", modifiers=()):
                states = [0] * 256
                for modifier in modifiers:
                    states[modifier] = 128
                return service.handleRequest({"method": method, "seqNum": 1,
                    "charCode": char, "keyCode": code, "repeatCount": 1,
                    "scanCode": 0, "isExtended": False, "keyStates": states})

            # Switching to cd_AI types like en_US: continue, keys straight in, hyphens kept.
            assert service.state.mode == "continue"
            typed = "".join(key(ord(c.upper()), ord(c)).get("commitString", "") for c in "ls -la")
            assert typed == "ls -la", typed
            assert key(9, method="filterKeyDown")["return"] is False  # nothing offered: Tab is the app's
            service.state.mode = "rewrite"  # the rest exercises rewrite
            service.state.change("")
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
            # Pending Tab leaves the original available instead of committing it.
            assert "commitString" not in key(9)
            reply = key(13)
            assert reply["commitString"] == "hello—world"
            assert reply["compositionString"] == ""
            for char in "draft":
                key(ord(char.upper()), ord(char))
            revision = service.state.revision
            worker_class.return_value.poll.return_value = (revision, {"text": "A nuanced draft."})
            assert key(0x75)["candidateList"] == []  # rewrite has no list: Tab converts in place
            worker_class.return_value.poll.return_value = None
            reply = key(9)
            assert "commitString" not in reply and reply["compositionString"] == "A nuanced draft.", reply
            reply = key(0x1B)  # Esc: your words again
            assert "commitString" not in reply and reply["compositionString"] == "draft", reply
            key(9)
            assert key(9)["commitString"] == "A nuanced draft."  # Tab again keeps it
            for char in "say hi":
                key(ord(char.upper()), ord(char))
            assert key(0x76, method="filterKeyDown")["return"]
            reply = key(0x76)
            assert service.state.mode == "continue" and "continue" in json.dumps(reply.get("showMessage")), reply
            assert reply["commitString"] == "say hi"  # continue types into the app: the held words go in
            assert worker_class.return_value.schedule.call_args.args[2] != "continue"  # mid-word: no suggestion yet
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
            key(0x76)  # instruct, starting empty: the words are in the app already
            assert service.state.mode == "instruct" and service.state.text == ""
            # Instruct: no request while typing; Enter sends; the next Enter inserts.
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
            service.handleRequest({"method": "onDeactivate"})
            worker_class.return_value.close.assert_called_once()
        sys.path.remove(temporary)
    print("PIME Python contract smoke passed, continue by default, live continue, F8, candidate lists, and agent questions included (native TSF typing: tests/desktop/windows)")


if __name__ == "__main__":
    main()
