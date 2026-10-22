"""A scripted stand-in for Claude Code's stream-json protocol (the G18 tests' agent).

It answers initialize, then serves turns until stdin closes, as Claude Code does. A turn
streams a partial draft, asks permission to run `git status`, and finishes with a result
that depends on the answer. With "slow" in the prompt it works until interrupted; with
"count" it reports how many turns this process has served and its session flags.
"""
import json
import queue
import sys
import threading
import time

inbox = queue.Queue()


def out(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def reader():
    for line in sys.stdin:
        inbox.put(json.loads(line))
    inbox.put(None)


def read(timeout=None):
    try:
        message = inbox.get(timeout=timeout)
    except queue.Empty:
        return None
    if message is None:
        sys.exit(0)
    if message.get("type") == "control_request" and message["request"]["subtype"] == "interrupt":
        out({"type": "control_response", "response": {"subtype": "success", "request_id": message["request_id"],
                                                      "response": {}}})
        raise KeyboardInterrupt
    return message


threading.Thread(target=reader, daemon=True).start()
init = read()
assert init["type"] == "control_request" and init["request"]["subtype"] == "initialize", init
out({"type": "control_response", "response": {"subtype": "success", "request_id": init["request_id"], "response": {}}})
session = " ".join(arg for i, arg in enumerate(sys.argv[1:]) if arg in ("--session-id", "--resume")
                   or sys.argv[i] in ("--session-id", "--resume"))
turns = 0
while True:
    prompt = read()
    assert prompt["type"] == "user", prompt
    text = prompt["message"]["content"]
    turns += 1
    out({"type": "system", "subtype": "init", "session_id": "fake"})
    try:
        if "count" in text:
            out({"type": "result", "subtype": "success", "is_error": False,
                 "result": "turn %d of this process (%s)" % (turns, session)})
            continue
        if "textbox" in text:  # call Claudish's textbox MCP server, as Claude Code would
            import asyncio
            config = json.load(open(sys.argv[sys.argv.index("--mcp-config") + 1]))["mcpServers"]["textbox"]

            async def search():
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client
                server = StdioServerParameters(command=config["command"], args=config["args"], env=config["env"])
                async with stdio_client(server) as streams, ClientSession(*streams) as client:
                    await client.initialize()
                    names = sorted(tool.name for tool in (await client.list_tools()).tools)
                    found = await client.call_tool("search", {"query": "budget"})
                    return names, found.content[0].text
            names, found = asyncio.run(search())
            out({"type": "control_request", "request_id": "perm-tb-%d" % turns, "request": {
                "subtype": "can_use_tool", "tool_name": "mcp__textbox__search", "input": {"query": "budget"}}})
            reply = read()
            assert reply["response"]["response"]["behavior"] == "allow", reply  # allowed by policy, no question
            out({"type": "result", "subtype": "success", "is_error": False,
                 "result": "%s | %s | caret seen: %s" % (",".join(names), found, "▮" in text)})
            continue
        if "slow" in text:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                read(timeout=deadline - time.monotonic())
        for chunk in ("Checking", " the branch"):
            out({"type": "stream_event", "event": {"type": "content_block_delta",
                                                   "delta": {"type": "text_delta", "text": chunk}}})
            time.sleep(0.2)
        out({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash",
                                                           "input": {"command": "git status"}}]},
             "parent_tool_use_id": None})
        out({"type": "control_request", "request_id": "perm-%d" % turns, "request": {
            "subtype": "can_use_tool", "tool_name": "Bash", "input": {"command": "git status"},
            "description": "Show the working tree status"}})
        reply = read()
        assert reply["type"] == "control_response" and reply["response"]["request_id"] == "perm-%d" % turns, reply
        decision = reply["response"]["response"]
        if decision["behavior"] == "allow":
            assert decision["updatedInput"] == {"command": "git status"}
            result = "The branch is clean—nothing to commit."
        else:
            result = "Understood—I left it alone. (%s)" % decision["message"]
        out({"type": "result", "subtype": "success", "is_error": False, "result": result})
    except KeyboardInterrupt:
        out({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": ""})
