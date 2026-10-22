"""Context providers: reference text gathered at invocation and handed to the model.

Providers come only from the user's config file, never from a request:
  {"type": "file", "path": "~/notes/style.md"}
  {"type": "command", "command": ["git", "-C", "~/repo", "diff", "main...HEAD"], "ttl": 30}
The request may add the text around the caret ("before"/"after").
"""
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

PROVIDER_KEYS = {"file": {"type", "name", "path", "ttl"},
                 "command": {"type", "name", "command", "ttl", "timeout", "cwd"}}


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
            if isinstance(command, str):
                command = shlex.split(command)
            if not (isinstance(command, list) and command and all(isinstance(part, str) for part in command)):
                raise ValueError('context command needs a "command" list or string')
            self.command = [os.path.expanduser(part) for part in command]
            self.timeout = float(spec.get("timeout", 5))
            self.cwd = os.path.expanduser(spec["cwd"]) if spec.get("cwd") else None
            self.name = spec.get("name") or " ".join(command)

    def read(self):
        if self.kind == "file":
            return self.path.read_text(encoding="utf-8", errors="replace")
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
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    self.cached = None
                    self.error = str(exc)
                self.expires = time.monotonic() + self.ttl
            return self.cached


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
