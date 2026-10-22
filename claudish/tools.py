"""Agentic instruct (G17): an instruction may call the profile's read-only MCP tools, then draft.

Profile: "tools": ["notes", {"server": "github", "trust": ["get_pull_request"]}] names entries of
mcp_servers. Only tools the server marks read-only (readOnlyHint) are offered, plus the ones the
user vouches for with "trust"; tools with side effects wait for an approval channel (G18). Every
call is listed in "consulted", the loop is bounded in steps and time, and the result is still
only a candidate.
"""
import json
import time

from .context import Provider

MAX_STEPS = 4
SEPARATOR = "__"  # tool names reach the model as server__tool


def field(item, name):
    """An MCP SDK field by its 2.x name (read_only_hint) or its 1.x/wire name (readOnlyHint)."""
    head, *rest = name.split("_")
    return getattr(item, name, None) or getattr(item, head + "".join(part.title() for part in rest), None)


def parse(spec):
    """A "tools" entry -> (server name, trusted tool names, denied tool names)."""
    if isinstance(spec, str):
        return spec, set(), set()
    if isinstance(spec, dict) and isinstance(spec.get("server"), str) and set(spec) <= {"server", "trust", "deny"}:
        lists = [spec.get(key) or [] for key in ("trust", "deny")]
        if all(isinstance(names, list) and all(isinstance(n, str) for n in names) for names in lists):
            return spec["server"], set(lists[0]), set(lists[1])
    raise ValueError('tools entries are server names or {"server": NAME, "trust": [TOOL, ...], "deny": [TOOL, ...]}')


def classify(tool, trust, deny):
    """read (runs), write (asks), destructive (asks every time), or denied (never offered)."""
    annotations = getattr(tool, "annotations", None)
    if tool.name in deny:
        return "denied"
    if field(annotations, "read_only_hint") or tool.name in trust:
        return "read"
    return "destructive" if field(annotations, "destructive_hint") else "write"


class Toolbox:
    def __init__(self, specs, servers, timeout=60):
        self.timeout = timeout
        self.servers = []
        for spec in specs:
            name, trust, deny = parse(spec)
            if name not in (servers or {}):
                raise ValueError('tools: server %r is not in "mcp_servers"' % name)
            if SEPARATOR in name:
                raise ValueError("tools: server names may not contain %r" % SEPARATOR)
            provider = Provider.__new__(Provider)
            provider.listing = True  # connection settings only; tools are chosen per call
            Provider.__init__(provider, {"type": "mcp", "server": name, "timeout": timeout}, None, servers)
            self.servers.append((name, trust, deny, provider))

    def run(self, ask, messages, approve=None, progress=None):
        """Run the loop. ask(messages, tools) -> the model's message (OpenAI shape).
        approve(server, tool, arguments, kind) -> (allowed, reason) is asked before each write or
        destructive call; without it those tools are not offered. progress(text) hears each call.
        Returns (final text, consulted, messages with the tool calls and results appended)."""
        import anyio
        return anyio.run(self._run, ask, messages, approve, progress)

    async def _run(self, ask, messages, approve, progress):
        from contextlib import AsyncExitStack

        import anyio
        from mcp import ClientSession
        from .context import connector
        consulted, kinds = [], {}
        spent = 0.0  # model and tool time; waiting for your answer does not count

        async def timed(call, *args):
            nonlocal spent
            started = time.monotonic()
            with anyio.fail_after(max(1.0, self.timeout - spent)):
                try:
                    return await call(*args)
                finally:
                    spent += time.monotonic() - started

        async with AsyncExitStack() as stack:
            sessions, offered = {}, []
            for name, trust, deny, provider in self.servers:
                streams = await stack.enter_async_context(connector(provider))
                session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
                await timed(session.initialize)
                sessions[name] = session
                for tool in (await timed(session.list_tools)).tools:
                    kind = classify(tool, trust, deny)
                    if kind == "denied" or (kind != "read" and approve is None):
                        continue  # side effects are only offered when someone can approve them
                    kinds[name + SEPARATOR + tool.name] = kind
                    offered.append({"type": "function", "function": {
                        "name": name + SEPARATOR + tool.name,
                        "description": (tool.description or "").strip()[:500],
                        "parameters": field(tool, "input_schema") or {"type": "object", "properties": {}}}})
            messages = list(messages)
            for step in range(MAX_STEPS + 1):
                final = step == MAX_STEPS or not offered or spent >= self.timeout
                reply = await timed(anyio.to_thread.run_sync, ask, messages, None if final else offered)
                calls = reply.get("tool_calls") or []
                if not calls:
                    return (reply.get("content") or "").strip(), consulted, messages
                messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls})
                for call in calls:
                    function = call.get("function") or {}
                    server, _, tool = (function.get("name") or "").partition(SEPARATOR)
                    kind = kinds.get(function.get("name"))
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                    except ValueError:
                        arguments = None
                    if kind is None or not isinstance(arguments, dict):
                        result = "error: unknown tool or invalid arguments"
                    else:
                        summary = "%s.%s(%s)" % (server, tool, ", ".join(
                            "%s=%s" % (k, json.dumps(v, ensure_ascii=False)[:40]) for k, v in arguments.items()))
                        allowed, reason = True, None
                        if kind != "read":
                            allowed, reason = await anyio.to_thread.run_sync(approve, server, tool, arguments, kind)
                        if not allowed:
                            result = "denied by the user" + (": " + reason if reason else "")
                        else:
                            consulted.append(summary)
                            if progress:
                                progress(summary)
                            try:
                                outcome = await timed(sessions[server].call_tool, tool, arguments)
                                result = "\n".join(block.text for block in outcome.content
                                                   if getattr(block, "type", "") == "text")[:8000]
                                if field(outcome, "is_error"):
                                    result = "error: " + result
                            except Exception as exc:  # a failed tool is information for the model
                                result = "error: %s" % (exc,)
                    messages.append({"role": "tool", "tool_call_id": call.get("id") or "", "content": result})
        raise RuntimeError("the tool loop did not finish")
