"""Profiles: one JSON file declaring backends and templates. Standard library only.

{
  "profile": "claude",
  "profiles": {
    "claude": {"backend": "claude", "claude_model": "claude-opus-5-5"},
    "ollama": {"backend": "openai", "model_url": "http://127.0.0.1:11434", "model": "your-model"},
    "local":  {"backend": "llama", "templates": "grand.json"}
  }
}

A key comes from an environment variable named by "api_key_env". With no file, no model
is set up (backend "none"): compose says so, and continue only types.
"""
import json
import os
from pathlib import Path

from .context import Binding, Context
from . import modes as invocation

BACKENDS = ("none", "llama", "openai", "claude", "claude-code", "codex", "command", "rules")
DEFAULTS = {"backend": "none", "model_url": "http://127.0.0.1:18766", "model": None, "api_key_env": None,
            "timeout": 3, "max_tokens": 64, "claude_model": "claude-opus-5-5", "templates": None,
            "context": None, "max_context_chars": 6000, "modes": None, "command": None, "hosted": None,
            "bindings": None, "look_command": None, "read_terminal": True, "tone": None, "helper": None, "launcher": None, "tools": None,
            "session_command": None}
TYPES = {"backend": str, "model_url": str, "model": str, "api_key_env": str, "timeout": (int, float),
         "max_tokens": int, "claude_model": str, "templates": str, "context": list, "max_context_chars": int, "modes": dict, "command": list, "hosted": bool, "bindings": list, "look_command": list, "read_terminal": bool, "tone": str, "helper": (list, dict), "launcher": list, "tools": list, "session_command": list}


def default_path():
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "claudish" / "config.json"


def resolve(path=None, profile=None, overrides=None):
    """Return (profile name, settings, templates, context) from the file, then non-None overrides.

    templates: the profile's templates file, read (modes.load), or None for the shipped ones;
    settings["modes"] becomes name -> {"profile"}: which profile answers a mode."""
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
        if entry.get("tone") == "fix":
            raise ValueError('profile %r: the tone "fix" is now "proofread" (it corrects and keeps your words)' % name)
        if "prompt" in entry:
            raise ValueError('profile %r: "prompt" is now "templates", a file in the shape of '
                             "claudish/templates.json (docs/configuration.md#templates)" % name)
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
    if settings["backend"] == "none" and any((overrides or {}).get(key) for key in ("model_url", "model")):
        settings["backend"] = "openai"  # a model server named with no backend: any OpenAI-compatible one
    if settings["backend"] not in BACKENDS:
        raise ValueError("backend must be one of: " + ", ".join(BACKENDS))
    if settings["backend"] in ("claude-code", "codex") and not settings["command"]:
        settings["command"] = ["claude" if settings["backend"] == "claude-code" else "codex"]
    if settings["backend"] in ("command", "claude-code", "codex"):
        command = settings["command"]
        if not (isinstance(command, list) and command and all(isinstance(part, str) for part in command)):
            raise ValueError('the command backend needs "command": ["program", "arg", ...] in the profile')
        settings["command"] = [os.path.expanduser(part) for part in command]
    templates = None
    if settings["templates"]:
        templates_path = Path(settings["templates"]).expanduser()
        if not templates_path.is_absolute() and not (overrides or {}).get("templates"):
            templates_path = base / templates_path  # Paths in a profile are relative to the file.
        templates = invocation.load(templates_path)
    modes = {}
    for mode, spec in (settings["modes"] or {}).items():
        # Which AI answers this mode (a small model for continue, a strong one for instructions);
        # what it is asked is in the templates.
        if not isinstance(spec, dict) or set(spec) != {"profile"}:
            raise ValueError('profile %r: mode %r takes only "profile" (its words, budget and candidates '
                             'are in "templates")' % (name, mode))
        if not isinstance(spec["profile"], str) or (known and spec["profile"] not in known):
            raise ValueError("profile %r: mode %r names profile %r, which is not in the config"
                             % (name, mode, spec["profile"]))
        modes[mode] = {"profile": spec["profile"]}
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
    return name, settings, templates, context


STARTER = {
    "about": [
        "cd_AI's profiles; \"profile\" is the one the service runs (cd_AI's settings change it too).",
        "claude: Anthropic's API, with the key saved in cd_AI's settings (`claudish settings`).",
        "ollama: any OpenAI-compatible server (Ollama, LM Studio, llama.cpp, a hosted API): set model_url,",
        "  and model when the server has several. A key: saved in the settings, or api_key_env.",
        "local: the llama.cpp server and Gemma 4 E4B that `claudish setup --profile local` installs.",
        "claude-code: Claude Code (a Claude subscription), kept running beside the service; picked in cd_AI's settings.",
        "codex: Codex (a ChatGPT subscription), kept running beside the service; picked in cd_AI's settings.",
        "agent: an agent CLI that reads the text on stdin (here Claude Code's `claude -p`).",
        "Profile keys: backend, model_url, model, api_key_env, timeout, max_tokens, claude_model,",
        "templates, context, max_context_chars, modes, command, hosted, bindings, look_command, read_terminal, tone, helper, launcher, tools, session_command. See docs/configuration.md.",
    ],
    "profile": "claude",
    "profiles": {
        "claude": {"backend": "claude", "claude_model": "claude-opus-5-5", "templates": "templates.json"},
        "ollama": {"backend": "openai", "model_url": "http://127.0.0.1:11434", "timeout": 30,
                   "templates": "templates.json"},
        "local": {"backend": "llama", "model_url": "http://127.0.0.1:18766", "timeout": 15, "templates": "templates.json"},
        "claude-code": {"backend": "claude-code", "command": ["claude"], "model": "haiku", "timeout": 30,
                        "templates": "templates.json"},
        "codex": {"backend": "codex", "command": ["codex"], "model": "gpt-6-luna", "timeout": 60,
                  "templates": "templates.json"},
        "agent": {"backend": "command", "timeout": 120, "command": ["claude", "-p", "--output-format", "text"]},
    },
}


# Beside the starter config: the templates a profile reads over cd_AI's own, to find and change.
STARTER_TEMPLATES = {
    "about": [
        "Templates over cd_AI's own (claudish/templates.json): this file names only what it changes,",
        "mode by mode and key by key. `claudish templates` prints what a profile ends up with. To switch",
        "tone, set a profile's \"tone\" in config.json: corporate (the default), salesman, critic, bard,",
        "proofread, or one named below. docs/configuration.md#templates has the rest.",
    ],
    "tones": {"named": {"mine": {
        "about": "A tone to edit: set \"tone\": \"mine\" in config.json, then rewrite this one.",
        "modes": {"rewrite": {
            "system": "Rewrite the user's text the way a weary pirate captain would say it: salty, theatrical, "
                      "one or two sentences. Keep the meaning: a yes stays a yes, a no stays a no, a question "
                      "stays a question. Keep every name, number, date, code term and URL exactly as written. "
                      "You are the writer, so never answer the text. Output only the rewritten text.",
            "examples": [["ok", "Aye, aye—'tis agreed, matey, and may the wind stay at our backs."]],
        }},
    }}},
}


def write_starter_templates(config_path):
    """The starter's templates.json beside a new config (its profiles read it); kept if there is one."""
    templates = Path(config_path).with_name("templates.json")
    templates.parent.mkdir(parents=True, exist_ok=True)
    if not templates.exists():
        templates.write_text(json.dumps(STARTER_TEMPLATES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_starter(path=None, profile=None):
    """Write the starter config, with profile (one of its profiles) as the default, and its
    templates.json beside it (kept if there is one); never overwrite a config. Returns the path."""
    path = Path(path or default_path())
    if path.exists():
        raise FileExistsError("%s already exists; edit it, or move it aside to start over" % path)
    write_starter_templates(path)
    path.write_text(json.dumps(dict(STARTER, profile=profile or STARTER["profile"]), indent=2) + "\n", encoding="utf-8")
    return path
