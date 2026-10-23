"""Profiles: one JSON file declaring backends and templates. Standard library only.

{
  "profile": "local",
  "profiles": {
    "local":  {"backend": "llama"},
    "ollama": {"backend": "openai", "model_url": "http://127.0.0.1:11434", "model": "qwen2.5:7b"},
    "claude": {"backend": "claude", "claude_model": "claude-opus-5-5", "prompt": "grand.json"}
  }
}

Keys are never stored here: name an environment variable with "api_key_env".
"""
import json
import os
from pathlib import Path

from .context import Binding, Context
from .model import load_prompt

BACKENDS = ("llama", "openai", "claude", "command", "rules")
DEFAULTS = {"backend": "llama", "model_url": "http://127.0.0.1:18766", "model": None, "api_key_env": None,
            "timeout": 3, "max_tokens": 64, "claude_model": "claude-opus-5-5", "prompt": None,
            "context": None, "max_context_chars": 6000, "modes": None, "command": None, "hosted": None,
            "bindings": None, "look_command": None, "read_terminal": True, "tone": None, "helper": None, "tools": None,
            "session_command": None}
TYPES = {"backend": str, "model_url": str, "model": str, "api_key_env": str, "timeout": (int, float),
         "max_tokens": int, "claude_model": str, "prompt": str, "context": list, "max_context_chars": int, "modes": dict, "command": list, "hosted": bool, "bindings": list, "look_command": list, "read_terminal": bool, "tone": str, "helper": list, "tools": list, "session_command": list}


def default_path():
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "claudish" / "config.json"


def resolve(path=None, profile=None, overrides=None):
    """Return (profile name, settings, prompt, context) from the file, then non-None overrides.

    settings["modes"] becomes name -> {"system", "examples", "max_tokens"} overrides for Rewriter."""
    settings, name, base, servers, known = dict(DEFAULTS), None, Path.cwd(), {}, set()
    if path is not None or default_path().is_file():
        path = Path(path or default_path())
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("cannot read %s: %s" % (path, exc))
        profiles = data.get("profiles") if isinstance(data, dict) else None
        if not isinstance(profiles, dict) or not profiles:
            raise ValueError('%s needs a "profiles" object' % path)
        known = set(profiles)
        name = profile or data.get("profile") or next(iter(profiles))
        if name not in profiles:
            raise ValueError("profile %r is not in %s (have: %s)" % (name, path, ", ".join(profiles)))
        servers = data.get("mcp_servers") or {}
        if not (isinstance(servers, dict) and all(isinstance(v, dict) for v in servers.values())):
            raise ValueError('"mcp_servers" must map names to server objects')
        entry = profiles[name]
        if not isinstance(entry, dict):
            raise ValueError("profile %r must be an object" % name)
        if "api_key" in entry:
            raise ValueError('profile %r: store keys in the environment and set "api_key_env" to the '
                             "variable's name" % name)
        unknown = sorted(set(entry) - set(DEFAULTS))
        if unknown:
            raise ValueError("profile %r: unknown keys %s" % (name, ", ".join(unknown)))
        for key, value in entry.items():
            if value is not None and (not isinstance(value, TYPES[key]) or (isinstance(value, bool) and TYPES[key] is not bool)):
                raise ValueError("profile %r: %s has the wrong type" % (name, key))
        settings.update(entry)
        base = path.parent
    elif profile:
        raise ValueError("--profile needs a config file (%s not found)" % default_path())
    settings.update({key: value for key, value in (overrides or {}).items() if value is not None})
    if settings["backend"] not in BACKENDS:
        raise ValueError("backend must be one of: " + ", ".join(BACKENDS))
    if settings["backend"] == "command":
        command = settings["command"]
        if not (isinstance(command, list) and command and all(isinstance(part, str) for part in command)):
            raise ValueError('the command backend needs "command": ["program", "arg", ...] in the profile')
        settings["command"] = [os.path.expanduser(part) for part in command]
    prompt = None
    if settings["prompt"]:
        prompt_path = Path(settings["prompt"]).expanduser()
        if not prompt_path.is_absolute() and not (overrides or {}).get("prompt"):
            prompt_path = base / prompt_path  # Template paths in a profile are relative to the file.
        prompt = load_prompt(prompt_path)
    modes = {}
    for mode, spec in (settings["modes"] or {}).items():
        if not isinstance(spec, dict) or set(spec) - {"prompt", "max_tokens", "candidates", "profile"}:
            raise ValueError('profile %r: mode %r takes only "prompt", "max_tokens", "candidates", and "profile"'
                             % (name, mode))
        override = {}
        if spec.get("profile") is not None:
            # Which AI answers this mode (a small model for continue, a strong one for instructions).
            if not isinstance(spec["profile"], str) or (known and spec["profile"] not in known):
                raise ValueError("profile %r: mode %r names profile %r, which is not in the config"
                                 % (name, mode, spec["profile"]))
            override["profile"] = spec["profile"]
        if spec.get("prompt"):
            mode_path = Path(spec["prompt"]).expanduser()
            override["system"], override["examples"] = load_prompt(mode_path if mode_path.is_absolute() else base / mode_path)
        if spec.get("max_tokens") is not None:
            if not isinstance(spec["max_tokens"], int) or isinstance(spec["max_tokens"], bool):
                raise ValueError("profile %r: mode %r max_tokens must be an integer" % (name, mode))
            override["max_tokens"] = spec["max_tokens"]
        if spec.get("candidates") is not None:
            if not (isinstance(spec["candidates"], int) and not isinstance(spec["candidates"], bool)
                    and 1 <= spec["candidates"] <= 5):
                raise ValueError("profile %r: mode %r candidates must be 1 to 5" % (name, mode))
            override["candidates"] = spec["candidates"]
        if mode not in ("rewrite", "continue", "instruct") and "system" not in override and "profile" not in override:
            raise ValueError('profile %r: new mode %r needs a "prompt"' % (name, mode))
        modes[mode] = override
    settings["modes"] = modes
    context = None
    if settings["context"]:
        if not all(isinstance(spec, dict) for spec in settings["context"]):
            raise ValueError("profile %r: context must be a list of objects" % name)
        context = Context(settings["context"], base, settings["max_context_chars"], servers)
    settings["bindings"] = [Binding(spec, base, servers) for spec in settings["bindings"] or []]
    for binding in settings["bindings"]:
        if binding.profile and binding.profile not in known:
            raise ValueError("profile %r: binding for %r names profile %r, which is not in the config"
                             % (name, binding.pattern, binding.profile))
    settings["mcp_servers"] = servers
    return name, settings, prompt, context


STARTER = {
    "about": [
        "Claudish profiles. Pick one with `claudish serve --profile NAME`; \"profile\" is the default.",
        "Keys never go in this file: name an environment variable with api_key_env.",
        "Profile keys: backend, model_url, model, api_key_env, timeout, max_tokens, claude_model,",
        "prompt, context, max_context_chars, modes, command, hosted, bindings, look_command, read_terminal, tone, helper, tools, session_command. See docs/configuration.md.",
    ],
    "profile": "local",
    "profiles": {
        "local": {"backend": "llama", "model_url": "http://127.0.0.1:18766"},
        "ollama": {"backend": "openai", "model_url": "http://127.0.0.1:11434", "model": "qwen2.5:7b"},
        "claude": {"backend": "claude", "claude_model": "claude-opus-5-5"},
        "agent": {"backend": "command", "timeout": 120, "command": ["claude", "-p", "--output-format", "text"]},
    },
}


def write_starter(path=None):
    """Write the starter config; never overwrite an existing one. Returns the path."""
    path = Path(path or default_path())
    if path.exists():
        raise FileExistsError("%s already exists; edit it, or move it aside to start over" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(STARTER, indent=2) + "\n", encoding="utf-8")
    return path
