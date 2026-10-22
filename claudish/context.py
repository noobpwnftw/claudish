"""Context providers: reference text gathered at invocation and handed to the model.

Providers come only from the user's config file, never from a request:
  {"type": "file", "path": "~/notes/style.md"}
  {"type": "command", "command": ["git", "-C", "~/repo", "diff", "main...HEAD"], "ttl": 30}
  {"type": "mcp", "command": ["github-mcp-server", "stdio"], "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"},
   "tool": "get_pull_request_diff", "arguments": {"owner": "o", "repo": "r", "pullNumber": 1}}
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
                 "mcp": {"type", "name", "command", "env", "cwd", "url", "transport", "headers",
                         "tool", "arguments", "resource", "ttl", "timeout"}}


class Provider:
    def __init__(self, spec, base):
        kind = spec.get("type")
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
            # "$NAME" values come from the environment, so tokens stay out of the config file.
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
            if bool(self.tool) == bool(self.resource):
                raise ValueError('mcp context needs exactly one of "tool" or "resource"')
            self.arguments = spec.get("arguments") or {}
            env = spec.get("env") or {}
            if not (isinstance(env, dict) and all(isinstance(v, str) for v in env.values())):
                raise ValueError("mcp env must map names to strings")
            # "$NAME" values come from the environment, so tokens stay out of the config file.
            self.env = {key: os.path.expandvars(value) for key, value in env.items()}
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


def read_mcp(provider):
    """Start the configured stdio MCP server, call one tool or read one resource, and return its text."""
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    def connect():
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

    async def fetch():
        with anyio.fail_after(provider.timeout):
            async with connect() as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
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


class Context:
    def __init__(self, specs=(), base=Path.cwd(), max_chars=6000):
        self.providers = [Provider(spec, base) for spec in specs]
        self.max_chars = max_chars

    def render(self, before="", after="", extra=()):
        """Return a block to append to the system prompt, or "" when there is no context."""
        return self.gather(before, after, extra)[0]

    def gather(self, before="", after="", extra=()):
        """(block, names of the providers that contributed); extra providers come from app bindings."""
        sections = []
        for provider in list(self.providers) + list(extra):
            text = provider.get()
            if text:
                sections.append((provider.name, text))
        if before or after:
            sections.append(("text around the caret", (before[-1500:] + "▮" + after[:500]).strip()))
        if not sections:
            return "", []
        budget, parts = self.max_chars, []
        for name, text in sections:
            if budget <= 0:
                break
            text = text[:budget]
            budget -= len(text)
            parts.append('<context name="%s">\n%s\n</context>' % (name.replace('"', "'"), text))
        block = ("\n\nReference context for this text. Use it for names, terms, and facts; "
                 "do not copy it into the rewrite unless the text refers to it.\n" + "\n".join(parts))
        return block, [name for name, _ in sections]


class Binding:
    """Context for one kind of text box: an app pattern, such as "firefox*" or "com.apple.Terminal"."""

    def __init__(self, spec, base=Path.cwd()):
        if not isinstance(spec, dict) or not isinstance(spec.get("app"), str) or set(spec) - {"app", "context"}:
            raise ValueError('a binding is {"app": "pattern", "context": [providers]}')
        self.pattern = spec["app"]
        self.providers = [Provider(item, base) for item in spec.get("context") or []]

    def matches(self, app):
        import fnmatch
        return bool(app) and fnmatch.fnmatch(app.lower(), self.pattern.lower())
