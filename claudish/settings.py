"""The settings window's model (G62): what it shows, and the few changes it makes to config.json.

The window offers the model (Claude with an API key, Claude Code's `claude` command for a Claude
subscription, Codex's `codex` command for a ChatGPT subscription, or any OpenAI-compatible API) and
the tone. The models map onto the starter's profiles: "claude", "claude-code", "codex", and
"ollama" for any OpenAI-compatible server.
A config whose default is another profile is shown as that profile and left to its file.
The key is saved by claudish/keys.py.
"""
import glob
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from . import config, keys
from .modes import TEMPLATES

CHOICES = {"claude": "claude", "claude-code": "claude-code", "codex": "codex", "server": "ollama"}  # choice -> profile
MANAGED = ("claude", "claude-code", "codex", "ollama", "local")  # the profiles whose tone the window sets
NO_CLAUDE_CODE = "claude was not found: install Claude Code, then log in"
NO_CODEX = "codex was not found: install Codex, then log in"


def command_path(name, extension_glob):
    """A CLI's full path, or None: on PATH, or where its installers put it (a login service may not
    have the shell's PATH, so a profile keeps the full path). extension_glob: its VS Code copy."""
    found = shutil.which(name)
    if found:
        return str(Path(found).absolute())  # the link, not its target: an update moves the target
    home = Path.home()
    npm = Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "npm"
    places = [home / ".local/bin" / name, home / ".local/bin" / (name + ".exe"), home / (".%s/local" % name) / name,
              home / (".%s/bin" % name) / name, Path("/usr/local/bin") / name, Path("/opt/homebrew/bin") / name,
              home / ".npm-global/bin" / name, npm / (name + ".cmd")]
    places += sorted((Path(p) for p in glob.glob(str(home / extension_glob))  # the command, not its helpers
                      if Path(p).name in (name, name + ".exe")), key=version_order, reverse=True)
    return next((str(p) for p in places if p.is_file() and os.access(p, os.X_OK)), None)


def version_order(path):
    """The newest extension first: its folder's version as numbers (2.1.310 after 2.1.99)."""
    import re
    return [int(part) for part in re.findall(r"\d+", str(path))]


def claude_code():
    """The `claude` command's full path, or None."""
    return command_path("claude", ".vscode*/extensions/anthropic.claude-code-*/resources/native-binary/claude*")


def codex():
    """The `codex` command's full path, or None."""
    return command_path("codex", ".vscode*/extensions/openai.chatgpt-*/bin/*/codex*")


def read(path=None):
    path = path or config.default_path()
    if not path.is_file():
        return dict(config.STARTER, profiles={k: dict(v) for k, v in config.STARTER["profiles"].items()})
    return json.loads(path.read_text(encoding="utf-8-sig"))


def key_state():
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "environment"
    return "saved" if keys.stored() else "missing"


def state(path=None):
    """What the window shows. Never the key itself: only whether there is one, and where."""
    data = read(path)
    profiles = data.get("profiles") or {}
    name = data.get("profile") or next(iter(profiles), None)
    entry = profiles.get(name) or {}
    choice = {"claude": "claude", "claude-code": "claude-code", "codex": "codex", "ollama": "server",
              "local": "local"}.get(name, "other")
    server = profiles.get("ollama") or config.STARTER["profiles"]["ollama"]
    tone = entry.get("tone") or "corporate"
    return {
        "profile": name, "choice": choice,
        "key": key_state(), "key_where": keys.where(),
        "server": {"url": server.get("model_url", ""), "model": server.get("model") or "",
                   "key": "saved" if keys.server_key(server.get("model_url", "")) else "missing"},
        "tone": tone, "own_words": tone not in TEMPLATES["tones"]["named"],
        "tones": [{"name": n, "about": t.get("about", "")} for n, t in TEMPLATES["tones"]["named"].items()],
        "config": str(path or config.default_path()),
        # The server cd_AI writes with must answer, or "Ready" would be a lie (a refused
        # connection on this computer answers at once).
        "server_problem": check_server(server.get("model_url", ""), server.get("model")) if choice == "server" else None,
        "server_models": listed(server.get("model_url", "")) if choice == "server" else [],
        "claude_code": None if claude_code() else NO_CLAUDE_CODE,  # what the Claude Code choice would say
        "codex": None if codex() else NO_CODEX,
        "command": (entry.get("command") or [None])[0] if choice in ("claude-code", "codex") else None,
    }


def check_key(key):
    """None when Anthropic accepts the key (a model listing: free, no text sent), else why not."""
    try:
        import anthropic
    except ImportError:
        return "the Anthropic SDK is missing from this install"
    try:
        # Anthropic's own address, whatever ANTHROPIC_BASE_URL says: the key goes nowhere else.
        anthropic.Anthropic(api_key=key, base_url="https://api.anthropic.com", timeout=10.0,
                            max_retries=0).models.list(limit=1)
    except anthropic.AuthenticationError:
        return "Anthropic did not accept that key"
    except anthropic.APIConnectionError as exc:  # the network, or this computer's certificates: say which
        cause = exc.__cause__ or exc
        return "Anthropic could not be reached to check it (%s: %s)" % (type(cause).__name__, str(cause)[:120])
    except anthropic.APIError as exc:
        return "Anthropic answered: %s" % getattr(exc, "message", exc)
    return None


LOADING = "loading"  # server_models: the server answers, and is still loading its model
UNAUTHORIZED = "unauthorized"  # server_models: it wants a (valid) API key


def server_models(url, key=None):
    """The models an OpenAI-compatible server at url has, LOADING while it is still loading one
    (llama.cpp answers 503 then), or None when nothing answers there. key: its API key, if any
    (by default the one saved for this address)."""
    from urllib.error import HTTPError
    from urllib.request import Request, build_opener, ProxyHandler
    key = key or keys.server_key(url)
    headers = {"Authorization": "Bearer " + key} if key else {}
    try:
        with build_opener(ProxyHandler({})).open(Request(url.rstrip("/") + "/v1/models", headers=headers),
                                                 timeout=5) as response:
            listing = json.load(response)
        return [m["id"] for m in listing.get("data", []) if isinstance(m, dict) and isinstance(m.get("id"), str)]
    except HTTPError as exc:
        return LOADING if exc.code == 503 else UNAUTHORIZED if exc.code in (401, 403) else None
    except Exception:
        return None


def listed(url, key=None):
    """The server's models, or none while it loads or when nothing answers."""
    models = server_models(url, key)
    return models if isinstance(models, list) else []


def check_server(url, model=None, key=None):
    """None when the server answers at url and has the model (or names none), else why not."""
    models = server_models(url, key)
    if models is None:
        return "nothing answers at %s" % url
    if models == UNAUTHORIZED:
        return "%s wants an API key, and did not accept this one" % url if key or keys.server_key(url) \
            else "%s wants an API key" % url
    if models == LOADING:
        return "the server at %s is still loading its model: try again in a moment" % url
    if model and models and model not in models:
        return "the server has no model %r; it has: %s" % (model, ", ".join(models))
    return None


def apply(changes, path=None):
    """Make the window's changes; ValueError (with words for the window) when one is not valid.
    The key is checked before it is saved, and a key Anthropic refuses is not saved."""
    if not isinstance(changes, dict) or not set(changes) <= {"choice", "key", "server", "tone"}:
        raise ValueError("unknown setting")
    path = path or config.default_path()
    data = read(path)
    profiles = data.setdefault("profiles", {})
    if "key" in changes:
        key = changes["key"]
        if not isinstance(key, str) or not key.strip() or len(key) > 400 or any(c.isspace() for c in key.strip()):
            raise ValueError("paste the whole key, without spaces")
        problem = check_key(key.strip())
        if problem:
            raise ValueError(problem)
        keys.store(key.strip())
    if "server" in changes:
        server = changes["server"]
        url, model, server_key = (server.get("url", ""), server.get("model", ""), server.get("key") or None) \
            if isinstance(server, dict) else ("", "", None)
        if server_key is not None and (not isinstance(server_key, str) or len(server_key) > 400
                                       or any(c.isspace() for c in server_key.strip())):
            raise ValueError("paste the whole key, without spaces")
        server_key = server_key.strip() if server_key else None
        parts = urlsplit(url.strip()) if isinstance(url, str) else None
        if not parts or parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("an address starts with http:// or https://, such as http://127.0.0.1:11434")
        if not isinstance(model, str) or len(model) > 200:
            raise ValueError("a model's name is a short string")
        if not model.strip():  # the server's only model, or a list to pick from
            models = listed(url.strip(), server_key)
            if len(models) != 1:
                raise ValueError("pick the model to use: " + ", ".join(models[:20]) if models else
                                 check_server(url.strip(), key=server_key) or "name the model to use")
            model = models[0]
        entry = profiles.setdefault("ollama", dict(config.STARTER["profiles"]["ollama"]))
        entry.update(model_url=url.strip().rstrip("/"), model=model.strip())
    if "choice" in changes and changes["choice"] not in CHOICES:
        raise ValueError("unknown choice")
    if changes.get("choice") == "server" or ("server" in changes and data.get("profile") == "ollama"):
        server = profiles.get("ollama", config.STARTER["profiles"]["ollama"])
        problem = check_server(server["model_url"], server.get("model"), changes.get("server", {}).get("key")
                               if isinstance(changes.get("server"), dict) else None)
        if problem:  # switching to a server that is not there would leave every rewrite failing
            raise ValueError(problem)
    if "server" in changes and server_key:  # accepted by the server: saved for its address only
        keys.store(server_key, keys.server_name(profiles["ollama"]["model_url"]))
    for choice, find, missing in (("claude-code", claude_code, NO_CLAUDE_CODE), ("codex", codex, NO_CODEX)):
        if changes.get("choice") == choice:
            command = find()
            if not command:  # like a server that is not there: no switch to a model that cannot answer
                raise ValueError(missing)
            # Kept running beside the service (claudish/warm.py); the full path, so the login service
            # finds it without the shell's PATH. Keep the profile's model, tone and other settings.
            entry = profiles.setdefault(choice, dict(config.STARTER["profiles"][choice]))
            entry.update(backend=choice, command=[command])
    if "choice" in changes:
        name = CHOICES[changes["choice"]]
        profiles.setdefault(name, dict(config.STARTER["profiles"][name]))
        data["profile"] = name
    if "tone" in changes:
        tone = changes["tone"]
        if not isinstance(tone, str) or len(tone) > 200 or "\n" in tone:
            raise ValueError("a tone is a name or a few words")
        tone = tone.strip()
        for name in MANAGED:
            if name in profiles:
                if tone in ("", "corporate"):
                    profiles[name].pop("tone", None)
                else:
                    profiles[name]["tone"] = tone
    if "key" in changes and "choice" not in changes and not path.is_file():
        # The page already shows Claude chosen: with no config yet, the key makes it so.
        profiles.setdefault("claude", dict(config.STARTER["profiles"]["claude"]))
        data["profile"] = "claude"
    if set(changes) - {"key"} or not path.is_file():
        if not path.is_file():
            config.write_starter_templates(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    return state(path)
