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
                 "mcp": {"type", "name", "command", "env", "cwd", "tool", "arguments", "resource", "ttl", "timeout"}}


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
        if kind == "file":
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

    async def fetch():
        with anyio.fail_after(provider.timeout):
            parameters = StdioServerParameters(command=provider.command[0], args=provider.command[1:],
                                               env={**os.environ, **provider.env}, cwd=provider.cwd)
            async with stdio_client(parameters) as (read_stream, write_stream):
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

    def render(self, before="", after=""):
        """Return a block to append to the system prompt, or "" when there is no context."""
        sections = []
        for provider in self.providers:
            text = provider.get()
            if text:
                sections.append((provider.name, text))
        if before or after:
            sections.append(("text around the caret", (before[-1500:] + "▮" + after[:500]).strip()))
        if not sections:
            return ""
        budget, parts = self.max_chars, []
        for name, text in sections:
            if budget <= 0:
                break
            text = text[:budget]
            budget -= len(text)
            parts.append('<context name="%s">\n%s\n</context>' % (name.replace('"', "'"), text))
        return ("\n\nReference context for this text. Use it for names, terms, and facts; "
                "do not copy it into the rewrite unless the text refers to it.\n" + "\n".join(parts))
