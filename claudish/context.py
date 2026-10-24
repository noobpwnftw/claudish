"""Context providers: reference text gathered at invocation and handed to the model.

Providers come only from the user's config file, never from a request:
  {"type": "file", "path": "~/notes/style.md"}
  {"type": "command", "command": ["git", "-C", "~/repo", "diff", "main...HEAD"], "ttl": 30}
  {"type": "mcp", "command": ["github-mcp-server", "stdio"], "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"},
   "tool": "get_file_contents", "arguments": {"owner": "o", "repo": "r", "path": "docs/STYLE.md"}}
The request may add the text around the caret ("before"/"after").
"""
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

PROVIDER_KEYS = {"file": {"type", "name", "path", "ttl"},
                 "command": {"type", "name", "command", "ttl", "timeout", "cwd"},
                 "mcp": {"type", "name", "server", "command", "env", "cwd", "url", "transport", "headers",
                         "tool", "arguments", "resource", "ttl", "timeout"}}


def from_server(spec, servers):
    """Expand {"server": NAME} with the config's mcp_servers entry (Claude-style command/args/env or url)."""
    if "server" not in spec:
        return spec
    server = (servers or {}).get(spec["server"])
    if server is None:
        raise ValueError('mcp server %r is not in "mcp_servers" (see `claudish mcp import`)' % spec["server"])
    spec = dict(spec)
    spec.pop("server")
    if server.get("url"):
        spec.setdefault("url", server["url"])
        spec.setdefault("transport", "sse" if server.get("type") == "sse" else "http")
        spec.setdefault("headers", server.get("headers") or {})
    else:
        spec.setdefault("command", [server["command"]] + list(server.get("args") or []))
        spec.setdefault("env", server.get("env") or {})
    spec.setdefault("name", spec.get("tool") or spec.get("resource"))
    return spec


class Provider:
    def __init__(self, spec, base, servers=None):
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
            if not str(spec["url"]).startswith(("http://", "https://")):
                raise ValueError("mcp url must be http:// or https://")
            self.url, self.command = spec["url"], None
            self.transport = spec.get("transport", "http")
            if self.transport not in ("http", "sse"):
                raise ValueError('mcp transport must be "http" (streamable HTTP) or "sse"')
            headers = spec.get("headers") or {}
            if not (isinstance(headers, dict) and all(isinstance(v, str) for v in headers.values())):
                raise ValueError("mcp headers must map names to strings")
            self.headers = {key: os.path.expandvars(value) for key, value in headers.items()}
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
            self.env = {key: os.path.expandvars(value) for key, value in env.items()}
            if getattr(self, "listing", False):
                self.name = spec.get("name") or "listing"
                return
            if bool(self.tool) == bool(self.resource):
                raise ValueError('mcp context needs exactly one of "tool" or "resource"')
            self.name = spec.get("name") or self.tool or self.resource
            if self.command is None:
                self.name = spec.get("name") or self.url

    def read(self):
        if self.kind == "file":
            return self.path.read_text(encoding="utf-8", errors="replace")
        if self.kind == "mcp":
            return read_mcp(self)
        # A list of arguments, no shell: the command is exactly what the config says.
        result = subprocess.run(self.command, capture_output=True, text=True, errors="replace",
                                timeout=self.timeout, cwd=self.cwd)
        if result.returncode != 0:
            raise RuntimeError("exit status %d: %s" % (result.returncode, result.stderr.strip()[-200:]))
        return result.stdout

    def get(self):
        """Cached text, or an error note: a failed provider must not block the rewrite."""
        with self.lock:
            if time.monotonic() >= self.expires:
                try:
                    self.cached = self.read().strip()
                except (OSError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as exc:
                    self.cached = None
                    self.error = str(exc)
                self.expires = time.monotonic() + self.ttl
            return self.cached


def connector(provider):
    """The MCP client transport for a provider: stdio for a started server, else SSE or streamable HTTP."""
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client
    if provider.command is None and provider.transport == "sse":
        from mcp.client.sse import sse_client
        return sse_client(provider.url, headers=provider.headers, timeout=provider.timeout)
    if provider.command is None:
        import httpx2
        from mcp.client.streamable_http import streamable_http_client
        client = httpx2.AsyncClient(headers=provider.headers, timeout=provider.timeout)
        return streamable_http_client(provider.url, http_client=client)
    return stdio_client(StdioServerParameters(command=provider.command[0], args=provider.command[1:],
                                              env={**os.environ, **provider.env}, cwd=provider.cwd))


def read_mcp(provider):
    """Start the configured stdio MCP server, call one tool or read one resource, and return its text."""
    import anyio
    from mcp import ClientSession

    async def fetch():
        with anyio.fail_after(provider.timeout):
            async with connector(provider) as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    if getattr(provider, "listing", False):
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

    try:
        return anyio.run(fetch)
    except TimeoutError:
        raise
    except Exception as exc:  # The SDK raises various types; a failed source must not break the rewrite.
        raise RuntimeError("MCP %s: %s" % (provider.name, exc))


def list_server(server, timeout=15):
    """{"tools": [(name, summary)], "resources": [uri]} for one mcp_servers entry."""
    provider = Provider.__new__(Provider)
    provider.listing = True
    Provider.__init__(provider, {"type": "mcp", "server": "_", "timeout": timeout}, Path.cwd(), {"_": server})
    return read_mcp(provider)


class Context:
    def __init__(self, specs=(), base=Path.cwd(), max_chars=6000, servers=None):
        self.providers = [Provider(spec, base, servers) for spec in specs]
        self.max_chars = max_chars

    def sections(self, extra=()):
        """[(name, text)]: what the providers (and the app's bindings, extra) contribute, within
        max_chars. The text around the caret is not one of them: the text box describes it."""
        found, budget = [], self.max_chars
        for provider in list(self.providers) + list(extra):
            if budget <= 0:
                break
            text = provider.get()
            if text:
                found.append((provider.name, text[:budget]))
                budget -= len(text[:budget])
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
