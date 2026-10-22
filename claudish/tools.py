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
    """A "tools" entry -> (server name, set of trusted tool names)."""
    if isinstance(spec, str):
        return spec, set()
    if isinstance(spec, dict) and isinstance(spec.get("server"), str) and set(spec) <= {"server", "trust"}:
        trust = spec.get("trust") or []
        if isinstance(trust, list) and all(isinstance(name, str) for name in trust):
            return spec["server"], set(trust)
    raise ValueError('tools entries are server names or {"server": NAME, "trust": [TOOL, ...]}')


class Toolbox:
    def __init__(self, specs, servers, timeout=60):
        self.timeout = timeout
        self.servers = []
        for spec in specs:
            name, trust = parse(spec)
            if name not in (servers or {}):
                raise ValueError('tools: server %r is not in "mcp_servers"' % name)
            if SEPARATOR in name:
                raise ValueError("tools: server names may not contain %r" % SEPARATOR)
            provider = Provider.__new__(Provider)
            provider.listing = True  # connection settings only; tools are chosen per call
            Provider.__init__(provider, {"type": "mcp", "server": name, "timeout": timeout}, None, servers)
            self.servers.append((name, trust, provider))

    def run(self, ask, messages):
        """Run the loop. ask(messages, tools) -> the model's message (OpenAI shape).
        Returns (final text, consulted)."""
        import anyio
        return anyio.run(self._run, ask, messages)

    async def _run(self, ask, messages):
        from contextlib import AsyncExitStack

        import anyio
        from mcp import ClientSession
        from .context import connector
        consulted, deadline = [], time.monotonic() + self.timeout
        with anyio.fail_after(self.timeout):
            async with AsyncExitStack() as stack:
                sessions, offered = {}, []
                for name, trust, provider in self.servers:
                    streams = await stack.enter_async_context(connector(provider))
                    session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
                    await session.initialize()
                    sessions[name] = session
                    for tool in (await session.list_tools()).tools:
                        if not (field(getattr(tool, "annotations", None), "read_only_hint") or tool.name in trust):
                            continue  # side effects need a per-call approval (G18)
                        offered.append({"type": "function", "function": {
                            "name": name + SEPARATOR + tool.name,
                            "description": (tool.description or "").strip()[:500],
                            "parameters": field(tool, "input_schema") or {"type": "object", "properties": {}}}})
                messages = list(messages)
                for step in range(MAX_STEPS + 1):
                    final = step == MAX_STEPS or not offered
                    reply = await anyio.to_thread.run_sync(ask, messages, None if final else offered)
                    calls = reply.get("tool_calls") or []
                    if not calls:
                        return (reply.get("content") or "").strip(), consulted
                    messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls})
                    for call in calls:
                        function = call.get("function") or {}
                        server, _, tool = (function.get("name") or "").partition(SEPARATOR)
                        allowed = any(o["function"]["name"] == function.get("name") for o in offered)
                        try:
                            arguments = json.loads(function.get("arguments") or "{}")
                        except ValueError:
                            arguments = None
                        if not allowed or not isinstance(arguments, dict):
                            result = "error: unknown tool or invalid arguments"
                        else:
                            consulted.append("%s.%s(%s)" % (server, tool, ", ".join(
                                "%s=%s" % (k, json.dumps(v, ensure_ascii=False)[:40]) for k, v in arguments.items())))
                            try:
                                with anyio.fail_after(max(1.0, deadline - time.monotonic())):
                                    outcome = await sessions[server].call_tool(tool, arguments)
                                result = "\n".join(block.text for block in outcome.content
                                                   if getattr(block, "type", "") == "text")[:8000]
                                if field(outcome, "is_error"):
                                    result = "error: " + result
                            except Exception as exc:  # a failed tool is information for the model
                                result = "error: %s" % (exc,)
                        messages.append({"role": "tool", "tool_call_id": call.get("id") or "", "content": result})
        raise RuntimeError("the tool loop did not finish")
