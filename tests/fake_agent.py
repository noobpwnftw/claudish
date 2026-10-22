"""A scripted stand-in for Claude Code's stream-json protocol (the G18 tests' agent).

It answers initialize, reads the prompt, streams a partial draft, asks permission to run
`git status`, and finishes with a result that depends on the answer. With "slow" in the
prompt it waits to be cancelled.
"""
import json
import sys
import time


def out(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def read():
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    return json.loads(line)


init = read()
assert init["type"] == "control_request" and init["request"]["subtype"] == "initialize", init
out({"type": "control_response", "response": {"subtype": "success", "request_id": init["request_id"], "response": {}}})
prompt = read()
assert prompt["type"] == "user", prompt
text = prompt["message"]["content"]
out({"type": "system", "subtype": "init", "session_id": "fake"})
if "slow" in text:
    time.sleep(60)
for chunk in ("Checking", " the branch"):
    out({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": chunk}}})
    time.sleep(0.2)
out({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "git status"}}]},
     "parent_tool_use_id": None})
out({"type": "control_request", "request_id": "perm-1", "request": {
    "subtype": "can_use_tool", "tool_name": "Bash", "input": {"command": "git status"},
    "description": "Show the working tree status"}})
reply = read()
assert reply["type"] == "control_response" and reply["response"]["request_id"] == "perm-1", reply
decision = reply["response"]["response"]
if decision["behavior"] == "allow":
    assert decision["updatedInput"] == {"command": "git status"}
    result = "The branch is clean—nothing to commit."
else:
    result = "Understood—I left it alone. (%s)" % decision["message"]
out({"type": "result", "subtype": "success", "is_error": False, "result": result})
