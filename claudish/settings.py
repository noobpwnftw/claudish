"""The settings window's model (G62): what it shows, and the few changes it makes to config.json.

The window offers three things (docs/research/2026-10-24-install-poll.md): the Claude key, the
voice, and a model server on this computer instead of Claude. They map onto the starter's
profiles: "claude", and "ollama" for any OpenAI-compatible server (Ollama, LM Studio, llama.cpp).
A config whose default is another profile is shown as that profile and left to its file.
The key is saved by claudish/keys.py and never written here.
"""
import json
import os
from urllib.parse import urlsplit

from . import config, keys
from .modes import TEMPLATES

CHOICES = {"claude": "claude", "server": "ollama"}  # the window's choice -> the starter profile it uses
MANAGED = ("claude", "ollama", "local")  # the profiles whose voice the window sets


def read(path=None):
    path = path or config.default_path()
    if not path.is_file():
        return dict(config.STARTER, profiles={k: dict(v) for k, v in config.STARTER["profiles"].items()})
    return json.loads(path.read_text(encoding="utf-8"))


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
    choice = {"claude": "claude", "ollama": "server", "local": "local"}.get(name, "other")
    server = profiles.get("ollama") or config.STARTER["profiles"]["ollama"]
    tone = entry.get("tone") or "corporate"
    return {
        "profile": name, "choice": choice,
        "key": key_state(), "key_where": keys.where(),
        "server": {"url": server.get("model_url", ""), "model": server.get("model") or ""},
        "tone": tone, "own_words": tone not in TEMPLATES["tones"]["named"],
        "tones": [{"name": n, "about": t.get("about", "")} for n, t in TEMPLATES["tones"]["named"].items()],
        "config": str(path or config.default_path()),
    }


def check_key(key):
    """None when Anthropic accepts the key (a model listing: free, no text sent), else why not."""
    try:
        import anthropic
    except ImportError:
        return "the Anthropic SDK is missing from this install"
    try:
        anthropic.Anthropic(api_key=key, timeout=10.0, max_retries=0).models.list(limit=1)
    except anthropic.AuthenticationError:
        return "Anthropic did not accept that key"
    except anthropic.APIConnectionError:
        return "Anthropic could not be reached to check it"
    except anthropic.APIError as exc:
        return "Anthropic answered: %s" % getattr(exc, "message", exc)
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
        url, model = (server.get("url", ""), server.get("model", "")) if isinstance(server, dict) else ("", "")
        parts = urlsplit(url.strip()) if isinstance(url, str) else None
        if not parts or parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("the server's address starts with http://, such as http://127.0.0.1:11434")
        if not isinstance(model, str) or not model.strip() or len(model) > 200:
            raise ValueError("name the model the server should run, such as qwen2.5:7b")
        entry = profiles.setdefault("ollama", dict(config.STARTER["profiles"]["ollama"]))
        entry.update(model_url=url.strip().rstrip("/"), model=model.strip())
    if "choice" in changes:
        if changes["choice"] not in CHOICES:
            raise ValueError("unknown choice")
        name = CHOICES[changes["choice"]]
        profiles.setdefault(name, dict(config.STARTER["profiles"][name]))
        data["profile"] = name
    if "tone" in changes:
        tone = changes["tone"]
        if not isinstance(tone, str) or len(tone) > 200 or "\n" in tone:
            raise ValueError("a voice is a name or a few words")
        tone = tone.strip()
        for name in MANAGED:
            if name in profiles:
                if tone in ("", "corporate"):
                    profiles[name].pop("tone", None)
                else:
                    profiles[name]["tone"] = tone
    if set(changes) - {"key"}:
        if not path.is_file():
            config.write_starter_templates(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    return state(path)
