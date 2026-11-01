"""The config file: how you write (tone, keys, hints) once, and the models as profiles.
Standard library only.

{
  "profile": "claude",
  "tone": "critic",
  "profiles": {
    "claude": {"backend": "claude", "model": "claude-opus-5-5"},
    "server": {"backend": "openai", "model_url": "http://127.0.0.1:11434", "model": "your-model"},
    "local":  {"backend": "llama", "templates": "grand.json"}
  }
}

A profile's own "tone" wins over the file's (a binding can pick such a profile for an app). A key
comes from cd_AI's settings or an environment variable named by "api_key_env". With no file, no
model is set up (backend "none"): compose says so, and continue only types.
"""
import json
import os
from pathlib import Path

from .context import Binding, Context
from . import modes as invocation

BACKENDS = ("none", "llama", "openai", "claude", "claude-code", "codex", "command", "rules")
DEFAULTS = {"backend": "none", "model_url": "http://127.0.0.1:18766", "model": None, "api_key_env": None,
            "timeout": 3, "templates": None,
            "context": None, "max_context_chars": 6000, "modes": None, "command": None,
            "bindings": None, "look_command": None, "read_terminal": True, "tone": None, "helper": None, "launcher": None, "tools": None,
            "session_command": None}
# The key that sends your words to the model, the default first; the other one puts them in as typed.
SUMMON_KEYS = ("Shift+Enter", "Enter")
TYPES = {"backend": str, "model_url": str, "model": str, "api_key_env": str, "timeout": (int, float),
         "templates": str, "context": list, "max_context_chars": int, "modes": dict, "command": list, "bindings": list, "look_command": list, "read_terminal": bool, "tone": str, "helper": (list, dict), "launcher": list, "tools": list, "session_command": list}


def default_path():
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "claudish" / "config.json"


def resolve(path=None, profile=None, overrides=None):
    """Return (profile name, settings, templates, context) from the file, then non-None overrides.

    templates: the profile's templates file, read (modes.load), or None for the shipped ones;
    settings["modes"] becomes name -> {"profile"}: which profile answers a mode."""
    settings, name, base, servers, known, entry = dict(DEFAULTS), None, Path.cwd(), {}, set(), None
    summon, hints = SUMMON_KEYS[0], True
    if path is not None or default_path().is_file():
        path = Path(path or default_path())
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ValueError("cannot read %s: %s" % (path, exc))
        profiles = data.get("profiles") if isinstance(data, dict) else None
        if not isinstance(profiles, dict) or not profiles:
            raise ValueError('%s needs a "profiles" object' % path)
        known = set(profiles)
        name = profile or data.get("profile") or next(iter(profiles))
        if name not in profiles:
            raise ValueError("profile %r is not in %s (have: %s)" % (name, path, ", ".join(profiles)))
        keys = data.get("keys") or {}
        if not (isinstance(keys, dict) and set(keys) <= {"summon"} and keys.get("summon", SUMMON_KEYS[0]) in SUMMON_KEYS):
            raise ValueError('"keys" takes "summon": "Enter" or "Shift+Enter" (the other key puts your words in)')
        summon = keys.get("summon", summon)
        hints = data.get("hints", True)
        if not isinstance(hints, bool):
            raise ValueError('"hints" is true or false (false: the panel only while something is pending)')
        tone = data.get("tone")
        if tone is not None and not isinstance(tone, str):
            raise ValueError('"tone" is a tone\'s name or a few words')
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
            raise ValueError("profile %r: unknown keys %s (docs/configuration.md lists a profile's keys; or move "
                             "%s aside, and `claudish init` writes a new one)" % (name, ", ".join(unknown), path))
        for key, value in entry.items():
            if value is not None and (not isinstance(value, TYPES[key]) or (isinstance(value, bool) and TYPES[key] is not bool)):
                raise ValueError("profile %r: %s has the wrong type" % (name, key))
        settings.update(entry)
        if not settings["tone"]:
            settings["tone"] = tone  # the file's tone, unless this profile has its own
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
    if settings["backend"] in ("command", "claude-code", "codex") or (settings["backend"] == "llama" and settings["command"]):
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
    settings["summon"], settings["hints"] = summon, hints
    return name, settings, templates, context


STARTER = {
    "about": [
        "cd_AI's config. \"profile\" is the model the service uses (cd_AI's settings switch it); \"tone\",",
        "\"keys\" and \"hints\" are how you write, for every profile. The profiles:",
        "claude: Anthropic's API, with the key saved in cd_AI's settings (`claudish settings`).",
        "claude-code, codex: a Claude or ChatGPT subscription, through its own command line.",
        "server: any OpenAI-compatible server (Ollama, LM Studio, llama.cpp, a hosted API).",
        "local: the llama.cpp server and Gemma 4 E4B that `claudish setup --profile local` installs.",
        "Everything else (bindings per app, context, tools, helpers): docs/configuration.md.",
    ],
    "profile": "claude",
    "profiles": {
        "claude": {"backend": "claude", "model": "claude-opus-5-5", "templates": "templates.json"},
        "claude-code": {"backend": "claude-code", "command": ["claude"], "model": "haiku", "timeout": 30,
                        "templates": "templates.json"},
        "codex": {"backend": "codex", "command": ["codex"], "model": "gpt-6-luna", "timeout": 60,
                  "templates": "templates.json"},
        "server": {"backend": "openai", "model_url": "http://127.0.0.1:11434", "timeout": 30,
                   "templates": "templates.json"},
        "local": {"backend": "llama", "model_url": "http://127.0.0.1:18766", "timeout": 15, "templates": "templates.json"},
    },
}


# Beside the starter config: the templates a profile reads over cd_AI's own, to find and change.
STARTER_TEMPLATES = {
    "about": [
        "Templates over cd_AI's own (claudish/templates.json): this file names only what it changes,",
        "mode by mode and key by key. `claudish templates` prints what a profile ends up with. To switch",
        "tone, set \"tone\" in config.json: corporate (the default), salesman, critic, bard, unhinged,",
        "proofread, or one named below. docs/configuration.md#templates has the rest.",
    ],
    "tones": {"named": {"mine": {
        "about": "A tone to edit: set \"tone\": \"mine\" in config.json, then rewrite this one.",
        # The voice only: cd_AI's job (keep the meaning, names and numbers; never answer) does the rest.
        "modes": {"rewrite": {
            "voice": "the way a weary pirate captain would say it: salty, theatrical",
            "length": "one or two sentences",
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


def save(data, path=None):
    """Write config data to path through a temporary file, so the running service never reads half
    a file; a new config gets the starter's templates.json beside it."""
    path = Path(path or default_path())
    if not path.is_file():
        write_starter_templates(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def plainly(error):
    """A config error without its advice on fixing the file (the settings window gives its own)."""
    return str(error).split(" (docs/configuration.md")[0]


def set_tone(data, tone, profile=None):
    """Set the tone profile writes in: its own when it has one, else the file's, for every profile
    without its own ("" or "corporate", the default, removes the file's)."""
    tone = tone.strip()
    entry = (data.get("profiles") or {}).get(profile)
    if isinstance(entry, dict) and entry.get("tone"):
        entry["tone"] = tone or "corporate"
        return
    data.pop("tone", None)
    if tone not in ("", "corporate"):
        data["tone"] = tone
