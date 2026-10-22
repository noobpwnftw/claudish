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

            for char in "hello-world":
                assert key(ord(char.upper()), ord(char), "filterKeyDown")["return"]
                reply = key(ord(char.upper()), ord(char))
            assert reply["compositionString"] == "hello—world"
            # A modifier and a shortcut must not consume or rewrite composition.
            assert not key(0x10, method="filterKeyDown")["return"]
            assert not key(ord("C"), method="filterKeyDown", modifiers=(0x11,))["return"]
            assert not key(ord("C"), method="filterKeyDown", modifiers=(0x11, 0x12))["return"]
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
            assert key(0x75)["candidateList"] == ["A nuanced draft."]
            worker_class.return_value.poll.return_value = None
            assert key(9)["commitString"] == "A nuanced draft."
            for char in "say hi":
                key(ord(char.upper()), ord(char))
            assert key(0x76, method="filterKeyDown")["return"]
            reply = key(0x76)
            assert service.state.mode == "continue" and "continue" in json.dumps(reply.get("showMessage")), reply
            assert worker_class.return_value.schedule.call_args.args[2] == "continue"
            key(0x76)
            worker_class.return_value.poll.return_value = (service.state.revision, {"text": "Hello—truly."})
            assert key(9)["commitString"] == "Hello—truly."
            worker_class.return_value.poll.return_value = None
            # Instruct: no request while typing; Enter sends; the next Enter inserts.
            calls = worker_class.return_value.schedule.call_count
            for char in "story":
                key(ord(char.upper()), ord(char))
            assert worker_class.return_value.schedule.call_count == calls
            reply = key(0x0D)
            assert service.state.working and "working" in json.dumps(reply.get("showMessage"))
            assert worker_class.return_value.schedule.call_args.kwargs["immediate"] is True
            assert "commitString" not in key(0x0D)  # still working
            worker_class.return_value.poll.return_value = (service.state.revision, {"text": "Once upon a time."})
            assert key(0x0D)["commitString"] == "Once upon a time."
            worker_class.return_value.poll.return_value = None
            service.handleRequest({"method": "onKeyboardStatusChanged", "opened": False})
            assert not key(ord("X"), ord("x"), "filterKeyDown")["return"]
            service.handleRequest({"method": "onDeactivate"})
            worker_class.return_value.close.assert_called_once()
        sys.path.remove(temporary)
    print("PIME Python contract smoke passed; native Windows TSF remains untested")


if __name__ == "__main__":
    main()
