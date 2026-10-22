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

from .context import Context
from .model import load_prompt

BACKENDS = ("llama", "openai", "claude", "rules")
DEFAULTS = {"backend": "llama", "model_url": "http://127.0.0.1:18766", "model": None, "api_key_env": None,
            "timeout": 3, "max_tokens": 64, "claude_model": "claude-opus-5-5", "prompt": None,
            "context": None, "max_context_chars": 6000, "modes": None}
TYPES = {"backend": str, "model_url": str, "model": str, "api_key_env": str, "timeout": (int, float),
         "max_tokens": int, "claude_model": str, "prompt": str, "context": list, "max_context_chars": int, "modes": dict}


def default_path():
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "claudish" / "config.json"


def resolve(path=None, profile=None, overrides=None):
    """Return (profile name, settings, prompt, context) from the file, then non-None overrides.

    settings["modes"] becomes name -> {"system", "examples", "max_tokens"} overrides for Rewriter."""
    settings, name, base = dict(DEFAULTS), None, Path.cwd()
    if path is not None or default_path().is_file():
        path = Path(path or default_path())
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("cannot read %s: %s" % (path, exc))
        profiles = data.get("profiles") if isinstance(data, dict) else None
        if not isinstance(profiles, dict) or not profiles:
            raise ValueError('%s needs a "profiles" object' % path)
        name = profile or data.get("profile") or next(iter(profiles))
        if name not in profiles:
            raise ValueError("profile %r is not in %s (have: %s)" % (name, path, ", ".join(profiles)))
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
            if value is not None and (not isinstance(value, TYPES[key]) or isinstance(value, bool)):
                raise ValueError("profile %r: %s has the wrong type" % (name, key))
        settings.update(entry)
        base = path.parent
    elif profile:
        raise ValueError("--profile needs a config file (%s not found)" % default_path())
    settings.update({key: value for key, value in (overrides or {}).items() if value is not None})
    if settings["backend"] not in BACKENDS:
        raise ValueError("backend must be one of: " + ", ".join(BACKENDS))
    prompt = None
    if settings["prompt"]:
        prompt_path = Path(settings["prompt"]).expanduser()
        if not prompt_path.is_absolute() and not (overrides or {}).get("prompt"):
            prompt_path = base / prompt_path  # Template paths in a profile are relative to the file.
        prompt = load_prompt(prompt_path)
    modes = {}
    for mode, spec in (settings["modes"] or {}).items():
        if not isinstance(spec, dict) or set(spec) - {"prompt", "max_tokens"}:
            raise ValueError('profile %r: mode %r takes only "prompt" and "max_tokens"' % (name, mode))
        override = {}
        if spec.get("prompt"):
            mode_path = Path(spec["prompt"]).expanduser()
            override["system"], override["examples"] = load_prompt(mode_path if mode_path.is_absolute() else base / mode_path)
        if spec.get("max_tokens") is not None:
            if not isinstance(spec["max_tokens"], int) or isinstance(spec["max_tokens"], bool):
                raise ValueError("profile %r: mode %r max_tokens must be an integer" % (name, mode))
            override["max_tokens"] = spec["max_tokens"]
        if mode not in ("rewrite", "continue", "instruct") and "system" not in override:
            raise ValueError('profile %r: new mode %r needs a "prompt"' % (name, mode))
        modes[mode] = override
    settings["modes"] = modes
    context = None
    if settings["context"]:
        if not all(isinstance(spec, dict) for spec in settings["context"]):
            raise ValueError("profile %r: context must be a list of objects" % name)
        context = Context(settings["context"], base, settings["max_context_chars"])
    return name, settings, prompt, context
