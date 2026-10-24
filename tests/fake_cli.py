"""Stand-ins for the warm backends' CLIs (claudish/warm.py), speaking their stdio protocols:

  python fake_cli.py claude ...      Claude Code's `claude -p --input-format stream-json`
  python fake_cli.py codex app-server ...   Codex's JSON-RPC app server

Each answer says how many requests this process (or thread) has seen, so tests can tell whether
requests stay independent. A prompt containing "slow" takes 3 s; "die" ends the process."""
import itertools
import json
import sys
import time


def claude():
    seen = 0
    for line in sys.stdin:
        content = json.loads(line)["message"]["content"]
        seen += 1
        if "die" in content:
            sys.exit(3)
        if "slow" in content:
            time.sleep(3)
        if seen == 1:
            print(json.dumps({"type": "system", "subtype": "init"}), flush=True)
        print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                          "result": "seen %d: %s" % (seen, content[-12:])}), flush=True)


def codex():
    threads, ids = {}, itertools.count(1)

    def send(message):
        print(json.dumps(message), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        method, ident, params = message.get("method"), message.get("id"), message.get("params") or {}
        if method == "initialize":
            send({"id": ident, "result": {"userAgent": "fake"}})
        elif method == "thread/start":
            if params.get("model") == "nope":
                send({"id": ident, "error": {"code": -32600, "message": "model not available"}})
                continue
            thread = "t%d" % next(ids)
            threads[thread] = [0, params.get("model")]
            send({"id": ident, "result": {"thread": {"id": thread}}})
            send({"method": "thread/started", "params": {"thread": {"id": thread}}})
        elif method == "turn/start":
            thread = params["threadId"]
            threads[thread][0] += 1
            text = params["input"][0]["text"]
            if "die" in text:
                sys.exit(3)
            send({"id": ident, "result": {"turn": {"id": "u1", "status": "inProgress"}}})
            if "slow" in text:
                time.sleep(3)
            send({"id": 99, "method": "item/commandExecution/requestApproval", "params": {}})  # declined
            send({"method": "item/completed", "params": {"item": {"type": "agentMessage",
                  "text": "%s turn %d model %s: %s" % (thread, threads[thread][0], threads[thread][1], text[-12:])}}})
            send({"method": "turn/completed", "params": {"turn": {"id": "u1", "status": "completed"}}})


if __name__ == "__main__":
    claude() if sys.argv[1] == "claude" else codex()
