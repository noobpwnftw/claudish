"""Context providers: reference text gathered at invocation and handed to the model.

Providers come only from the user's config file, never from a request:
  {"type": "file", "path": "~/notes/style.md"}
  {"type": "command", "command": ["git", "-C", "~/repo", "diff", "main...HEAD"], "ttl": 30}
  {"type": "mcp", "command": ["github-mcp-server", "stdio"], "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"},
   "tool": "get_file_contents", "arguments": {"owner": "o", "repo": "r", "path": "docs/STYLE.md"}}
The request may add the text around the caret ("before"/"after").
"""
import os
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path

PROVIDER_KEYS = {"file": {"type", "name", "path", "ttl"},
                 "command": {"type", "name", "command", "ttl", "timeout", "cwd"},
                 "mcp": {"type", "name", "server", "command", "env", "cwd", "url", "transport", "headers",
                         "tool", "arguments", "resource", "ttl", "timeout"}}


VARIABLE = re.compile(r"\$(?:\{(\w+)(?::-([^}]*))?\}|(\w+))")


def expanded(value, missing=None):
    """$NAME, ${NAME} and ${NAME:-default} from this environment, as Claude Code expands them. A
    variable that is not set and has no default is added to missing (or raises when missing is None)."""
    def one(match):
        name = match.group(1) or match.group(3)
        if name in os.environ:
            return os.environ[name]
        if match.group(2) is not None:
            return match.group(2)
        if missing is None:
            raise ValueError("%s is not set in the environment cd_AI runs in" % name)
        missing.append(name)
        return match.group(0)
    return VARIABLE.sub(one, value)


def variables(value):
    """The environment variables a value needs: those it names without a default ($NAME, ${NAME};
    not ${NAME:-x}), as expanded() reads them."""
    return [m.group(1) or m.group(3) for m in VARIABLE.finditer(value) if m.group(2) is None]


def for_agent(value):
    """A value as Claude Code expands it itself: $NAME written ${NAME} (its own config does not take
    the bare form); the secret stays out of the config file Claudish writes."""
    return VARIABLE.sub(lambda m: m.group(0) if m.group(1) else "${%s}" % m.group(3), value)


def from_server(spec, servers):
    """Expand {"server": NAME} with the config's mcp_servers entry (Claude-style command/args/env or url)."""
    if "server" not in spec:
        return spec
    server = (servers or {}).get(spec["server"])
    if server is None:
        raise ValueError('mcp server %r is not in "mcp_servers" (see `claudish mcp import`)' % spec["server"])
    spec = dict(spec)
    name = spec.pop("server")
    if server.get("url"):
        spec.setdefault("url", server["url"])
        if server.get("type") == "ws":
            raise ValueError('mcp server %r: a WebSocket server ("type": "ws") is not supported' % name)
        spec.setdefault("transport", "sse" if server.get("type") == "sse" else "http")
        spec.setdefault("headers", server.get("headers") or {})
    elif isinstance(server.get("command"), str) and server["command"]:
        spec.setdefault("command", [server["command"]] + list(server.get("args") or []))
        spec.setdefault("env", server.get("env") or {})
    else:
        raise ValueError('mcp server %r needs a "command" (a program) or a "url"' % name)
    spec.setdefault("name", spec.get("tool") or spec.get("resource"))
    return spec


class Provider:
    def __init__(self, spec, base, servers=None, listing=False):
        """listing: an MCP server's connection settings only, for listing its tools and resources."""
        self.listing = listing
        kind = spec.get("type")
        if kind == "mcp":
            spec = from_server(spec, servers)
        if kind not in PROVIDER_KEYS:
            raise ValueError("context type must be one of: " + ", ".join(PROVIDER_KEYS))
        unknown = sorted(set(spec) - PROVIDER_KEYS[kind])
        if unknown:
            raise ValueError("context %s: unknown keys %s" % (kind, ", ".join(unknown)))
        self.kind = kind
        self.ttl = float(spec.get("ttl", 30))
        self.lock = threading.Lock()
        self.cached, self.expires = None, 0.0
        if kind == "mcp" and spec.get("url"):
            # An app that exposes MCP on a local socket: connect instead of starting a server.
            if spec.get("command"):
                raise ValueError('mcp context takes "command" (stdio) or "url", not both')
            if not str(spec["url"]).startswith(("http://", "https://", "$")):
                raise ValueError("mcp url must be http:// or https://")
            self.url, self.command = spec["url"], None
            self.transport = spec.get("transport", "http")
            if self.transport not in ("http", "sse"):
                raise ValueError('mcp transport must be "http" (streamable HTTP) or "sse"')
            headers = spec.get("headers") or {}
            if not (isinstance(headers, dict) and all(isinstance(v, str) for v in headers.values())):
                raise ValueError("mcp headers must map names to strings")
            self.headers = dict(headers)  # $NAME and ${NAME:-default} filled in when it connects
            self.timeout = float(spec.get("timeout", 5))
            self.cwd, self.name = None, spec.get("name") or spec["url"]
        elif kind == "file":
            if not isinstance(spec.get("path"), str):
                raise ValueError('context file needs a "path"')
            self.path = Path(os.path.expanduser(spec["path"]))
            if not self.path.is_absolute():
                self.path = base / self.path
            self.name = spec.get("name") or self.path.name
        else:
            command = spec.get("command")
            if isinstance(command, str) and command.strip():
                # Windows parses a command line itself (CreateProcess); POSIX shlex would eat backslashes.
                command = command if os.name == "nt" else [os.path.expanduser(part) for part in shlex.split(command)]
            elif isinstance(command, list) and command and all(isinstance(part, str) for part in command):
                command = [os.path.expanduser(part) for part in command]
            else:
                raise ValueError('context command needs a "command" list or string')
            self.command = command
            self.timeout = float(spec.get("timeout", 5))
            self.cwd = os.path.expanduser(spec["cwd"]) if spec.get("cwd") else None
            self.name = spec.get("name") or (command if isinstance(command, str) else " ".join(command))
        if kind == "mcp":
            try:
                import mcp  # noqa: F401  Optional dependency: pip install "claudish-ime[mcp]"
            except ImportError:
                raise ValueError('mcp context needs the MCP SDK: pip install "claudish-ime[mcp]"')
            if isinstance(self.command, str):
                raise ValueError('mcp "command" must be a list on Windows: ["program", "arg", ...]')
            if self.command is None and (spec.get("env") or spec.get("cwd")):
                raise ValueError("mcp env/cwd apply to a started server, not a url")
            self.tool, self.resource = spec.get("tool"), spec.get("resource")
            self.arguments = spec.get("arguments") or {}
            env = spec.get("env") or {}
            if not (isinstance(env, dict) and all(isinstance(v, str) for v in env.values())):
                raise ValueError("mcp env must map names to strings")
            self.env = dict(env)  # filled in when it starts (an unset variable says so then)
            if self.listing:
                self.name = spec.get("name") or "listing"
                return
            if bool(self.tool) == bool(self.resource):
                raise ValueError('mcp context needs exactly one of "tool" or "resource"')
            self.name = spec.get("name") or self.tool or self.resource
            if self.command is None:
                self.name = spec.get("name") or self.url

    def read(self):
        if self.kind == "file":
            return read_file(self.path, READ_LIMIT)
        if self.kind == "mcp":
            return read_mcp(self)
        # A list of arguments, no shell: the command is exactly what the config says.
        return run_bounded(self.command, self.timeout, self.cwd, READ_LIMIT)

    def get(self):
        """Cached text, or an error note: a failed provider must not block the rewrite."""
        with self.lock:
            if time.monotonic() >= self.expires:
                try:
                    self.cached, self.error = self.read().strip(), None
                except (OSError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as exc:
                    self.cached = None
                    self.error = str(exc)
                self.expires = time.monotonic() + self.ttl
            return self.cached


READ_LIMIT = 256 * 1024  # bytes read from a file or a command: far more than any request sends


def read_file(path, limit):
    """A regular file's first limit bytes, as text: never a FIFO or a device, which would wait (or
    never end) with the request waiting on it."""
    import stat
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(descriptor, "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            raise OSError("%s is not a regular file" % path)
        return file.read(limit).decode("utf-8", errors="replace")


def run_bounded(argv, timeout, cwd, limit):
    """A command's output (its first limit bytes), within timeout: in a process group of its own,
    ended with everything it started, so neither a child left in the background nor endless output
    holds the request."""
    windows = os.name == "nt"
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               cwd=cwd, start_new_session=not windows,
                               creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if windows else 0)
    out, err = [], []
    readers = [threading.Thread(target=lambda: out.append(process.stdout.read(limit)), daemon=True),
               threading.Thread(target=lambda: err.append(process.stderr.read(4096)), daemon=True)]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None and readers[0].is_alive():  # running, and still writing what we read
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(argv, timeout)
            time.sleep(0.02)
    finally:
        end_group(process, windows)
        for reader in readers:
            reader.join(1)
    text = (out[0] if out else b"").decode("utf-8", errors="replace")
    if process.returncode not in (0, None) and not (out and len(out[0]) >= limit):  # cut at the limit: ours, not its failure
        said = (err[0] if err else b"").decode("utf-8", errors="replace")
        raise RuntimeError("exit status %d: %s" % (process.returncode, said.strip()[-200:]))
    return text


def end_group(process, windows):
    """The command and whatever it started; then it is waited for."""
    try:
        if windows:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, timeout=5)
        else:
            import signal
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass  # all ended already
    try:
        process.wait(5)
    except subprocess.TimeoutExpired:
        pass


def connector(provider):
    """The MCP client transport for a provider: stdio for a started server, else SSE or streamable HTTP."""
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client
    # Variables now (Claude Code's forms): one that is not set fails this server, by name, rather
    # than reaching it as the text "$GITHUB_TOKEN".
    if provider.command is None:
        url = expanded(provider.url)
        headers = {key: expanded(value) for key, value in provider.headers.items()}
    if provider.command is None and provider.transport == "sse":
        from mcp.client.sse import sse_client
        return sse_client(url, headers=headers, timeout=provider.timeout)
    if provider.command is None:
        import httpx2
        from mcp.client.streamable_http import streamable_http_client
        client = httpx2.AsyncClient(headers=headers, timeout=provider.timeout)
        return streamable_http_client(url, http_client=client)
    command = [expanded(part) for part in provider.command]
    return stdio_client(StdioServerParameters(command=command[0], args=command[1:],
                                              env={**os.environ, **{key: expanded(value) for key, value in provider.env.items()}},
                                              cwd=provider.cwd))


def read_mcp(provider):
    """Connect to the provider's MCP server (started over stdio, or at its URL), call one tool or read
    one resource, and return its text."""
    import anyio
    from mcp import ClientSession

    async def fetch():
        with anyio.fail_after(provider.timeout):
            async with connector(provider) as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    if provider.listing:
                        tools = (await session.list_tools()).tools
                        try:
                            resources = (await session.list_resources()).resources
                        except Exception:  # Not every server offers resources.
                            resources = []
                        return {"tools": [(tool.name, (tool.description or "").strip().split("\n")[0]) for tool in tools],
                                "resources": [str(resource.uri) for resource in resources]}
                    if provider.tool:
                        result = await session.call_tool(provider.tool, provider.arguments)
                        if getattr(result, "is_error", False) or not hasattr(result, "content"):
                            raise RuntimeError("MCP tool %s failed" % provider.tool)
                        return "\n".join(block.text for block in result.content if getattr(block, "type", "") == "text")
                    result = await session.read_resource(provider.resource)
                    return "\n".join(item.text for item in getattr(result, "contents", []) if getattr(item, "text", None))

    # On a thread of its own: the SDK's shutdown of a server that hangs takes seconds more after the
    # timeout, which the request does not wait for (the server still ends, in the background).
    import threading
    done, outcome = threading.Event(), {}

    def run():
        try:
            outcome["value"] = anyio.run(fetch)
        except BaseException as exc:
            outcome["error"] = exc
        done.set()
    threading.Thread(target=run, daemon=True).start()
    if not done.wait(provider.timeout + 0.5) or isinstance(outcome.get("error"), TimeoutError):
        raise TimeoutError("timed out after %g s" % provider.timeout)
    if "error" in outcome:  # The SDK raises various types; a failed source must not break the rewrite.
        raise RuntimeError("MCP %s: %s" % (provider.name, outcome["error"]))
    return outcome["value"]


def list_server(server, timeout=15, name="_"):
    """{"tools": [(name, summary)], "resources": [uri]} for one mcp_servers entry (named in errors)."""
    return read_mcp(Provider({"type": "mcp", "server": name, "timeout": timeout}, Path.cwd(), {name: server}, listing=True))


class Context:
    def __init__(self, specs=(), base=Path.cwd(), max_chars=6000, servers=None):
        self.providers = [Provider(spec, base, servers) for spec in specs]
        self.max_chars = max_chars

    def sections(self, extra=(), failed=None, max_chars=None):
        """[(name, text)]: what the providers (and the app's bindings, extra) contribute, within
        max_chars (the answering profile's; else this context's). The text around the caret is not
        one of them: the text box describes it. failed: a list that gets (name, why) for each
        provider that could not be read."""
        found, budget = [], self.max_chars if max_chars is None else max_chars
        for provider in list(self.providers) + list(extra):
            if budget <= 0:
                break
            text = provider.get()
            if text:
                found.append((provider.name, text[:budget]))
                budget -= len(text[:budget])
            elif text is None and failed is not None:
                failed.append((provider.name, getattr(provider, "error", None) or "unavailable"))
        return found


class Binding:
    """A kind of text box, by app pattern ("thunderbird*", "com.apple.Terminal"): the context it adds,
    and the profile that answers there (which AI: its backend, tone, tools, and helper)."""

    def __init__(self, spec, base=Path.cwd(), servers=None):
        if (not isinstance(spec, dict) or not isinstance(spec.get("app"), str) or set(spec) - {"app", "context", "profile"}
                or not isinstance(spec.get("profile", ""), str)):
            raise ValueError('a binding is {"app": "pattern", "context": [providers], "profile": "name"}')
        self.pattern = spec["app"]
        self.profile = spec.get("profile")
        self.providers = [Provider(item, base, servers) for item in spec.get("context") or []]

    def matches(self, app):
        import fnmatch
        return bool(app) and fnmatch.fnmatch(app.lower(), self.pattern.lower())
