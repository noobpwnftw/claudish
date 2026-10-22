"""Agentic instruct (G17): an instruction may call the profile's read-only MCP tools, then draft.

Profile: "tools": ["notes", {"server": "github", "trust": ["get_pull_request"]}] names entries of
mcp_servers. Only tools the server marks read-only (readOnlyHint) are offered, plus the ones the
user vouches for with "trust"; tools with side effects wait for an approval channel (G18). Every
call is listed in "consulted", the loop is bounded in steps and time, and the result is still
only a candidate. Claudish's own read-only tools (the text box) join them, with or without MCP.
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

    def run(self, ask, messages, approve=None, progress=None, local=None):
        """Run the loop. ask(messages, tools) -> the model's message (OpenAI shape).
        approve(server, tool, arguments, kind) -> (allowed, reason) is asked before each write or
        destructive call; without it those tools are not offered. progress(text) hears each call.
        local: {"server__tool": (description, parameters, function(arguments) -> text)}, read-only
        tools served by Claudish itself (the text box). MCP servers need the SDK; local tools do not.
        Returns (final text, consulted, messages with the tool calls and results appended)."""
        from contextlib import ExitStack
        consulted, kinds, callers, offered = [], {}, {}, []
        spent = 0.0  # model and tool time; waiting for your answer does not count

        def timed(call, *args):
            nonlocal spent
            started = time.monotonic()
            try:
                return call(*args)
            finally:
                spent += time.monotonic() - started

        def offer(name, description, parameters):
            offered.append({"type": "function", "function": {
                "name": name, "description": (description or "").strip()[:500],
                "parameters": parameters or {"type": "object", "properties": {}}}})

        for name, (description, parameters, function) in (local or {}).items():
            kinds[name], callers[name] = "read", function
            offer(name, description, parameters)
        with ExitStack() as stack:
            if self.servers:
                from anyio.from_thread import start_blocking_portal
                portal = stack.enter_context(start_blocking_portal())
                for name, trust, deny, provider in self.servers:
                    limit = max(1.0, self.timeout - spent)
                    session = stack.enter_context(portal.wrap_async_context_manager(opened(provider, limit)))
                    for tool in timed(portal.call, listed, session, max(1.0, self.timeout - spent)):
                        kind = classify(tool, trust, deny)
                        if kind == "denied" or (kind != "read" and approve is None):
                            continue  # side effects are only offered when someone can approve them
                        full = name + SEPARATOR + tool.name
                        if full in kinds:
                            continue  # Claudish's own tools come first
                        kinds[full] = kind
                        callers[full] = (lambda arguments, session=session, tool=tool.name: timed(
                            portal.call, called, session, tool, arguments, max(1.0, self.timeout - spent)))
                        offer(full, tool.description, field(tool, "input_schema"))
            messages = list(messages)
            for step in range(MAX_STEPS + 1):
                final = step == MAX_STEPS or not offered or spent >= self.timeout
                reply = timed(ask, messages, None if final else offered)
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
                            allowed, reason = approve(server, tool, arguments, kind)
                        if not allowed:
                            result = "denied by the user" + (": " + reason if reason else "")
                        else:
                            consulted.append(summary)
                            if progress:
                                progress(summary)
                            try:
                                result = str(callers[function["name"]](arguments))[:8000]
                            except Exception as exc:  # a failed tool is information for the model
                                result = "error: %s" % (exc,)
                    messages.append({"role": "tool", "tool_call_id": call.get("id") or "", "content": result})
        raise RuntimeError("the tool loop did not finish")


def opened(provider, limit):
    """An initialized MCP client session for a configured server (an async context manager)."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session():
        import anyio
        from mcp import ClientSession
        from .context import connector
        async with connector(provider) as streams:
            async with ClientSession(streams[0], streams[1]) as client:
                with anyio.fail_after(limit):
                    await client.initialize()
                yield client
    return session()


async def listed(session, limit):
    import anyio
    with anyio.fail_after(limit):
        return (await session.list_tools()).tools


async def called(session, tool, arguments, limit):
    import anyio
    with anyio.fail_after(limit):
        outcome = await session.call_tool(tool, arguments)
    text = "\n".join(block.text for block in outcome.content if getattr(block, "type", "") == "text")
    return "error: " + text if field(outcome, "is_error") else text
