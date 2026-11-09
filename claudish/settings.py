"""The settings window's model (G62): what it shows, and the few changes it makes to config.json.

The window offers the model (Claude with an API key, Claude Code's `claude` command for a Claude
subscription, Codex's `codex` command for a ChatGPT subscription, or any OpenAI-compatible API), the
tone, the key that asks the model, and whether the panel shows hints. The models map onto the
starter's profiles: "claude", "claude-code", "codex", and "server" for any OpenAI-compatible server.
A config whose default is another profile is shown as that profile and left to its file. The keys
and hints are the file's, for every profile; the tone is the one the profile in use reads (its own,
else the file's).
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

CHOICES = {"claude": "claude", "claude-code": "claude-code", "codex": "codex", "server": "server"}  # choice -> profile
NO_CLAUDE_CODE = "the claude command was not found: install Claude Code, then log in"
NO_CODEX = "the codex command was not found: install Codex, then log in"


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
    places += sorted((Path(p) for p in glob.glob(str(home / ".nvm/versions/node/*/bin" / name))),
                     key=version_order, reverse=True)  # nvm's npm: the newest node first
    places += sorted((Path(p) for p in glob.glob(str(home / extension_glob))  # the command, not its helpers
                      if Path(p).name in (name, name + ".exe")), key=version_order, reverse=True)
    return next((str(p) for p in places if p.is_file() and os.access(p, os.X_OK)), None) or from_shell(name)


SHELL_ANSWERS = {}  # name -> (when, path): the shell asked again after SHELL_SECONDS
SHELL_SECONDS = 30


def from_shell(name):
    """The command where your own shell finds it: a login service has a short PATH, and node
    managers (volta, fnm, asdf, mise, ...) put their commands on the shell's. None on Windows, or
    when the shell does not answer within a few seconds."""
    if os.name == "nt":
        return None
    import time
    shell_env = os.environ.get("SHELL")
    asked = SHELL_ANSWERS.get((name, shell_env))
    if asked and time.monotonic() - asked[0] < SHELL_SECONDS:  # the settings page asks at every look
        return asked[1]
    found = ask_shell(name, shell_env)
    SHELL_ANSWERS[(name, shell_env)] = (time.monotonic(), found)
    return found


def ask_shell(name, shell):
    import pwd
    import subprocess
    shell = shell or pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh"
    try:
        # Its own session: an interactive shell takes the terminal's foreground, and one killed at
        # the timeout would leave a terminal caller (doctor) stopped.
        done = subprocess.run([shell, "-lic", "command -v %s" % name], stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=5, start_new_session=True)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in reversed(done.stdout.splitlines()):  # after anything the shell's startup files print
        line = line.strip()
        if line.startswith("/") and os.path.basename(line) == name and os.path.isfile(line) and os.access(line, os.X_OK):
            return line
    return None


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


def located(program):
    """A Claude Code or Codex command where it is, or where an update moved it (the CLI, or its
    VS Code extension's copy); any other program as given."""
    program = os.path.expanduser(program)
    if os.path.exists(program):
        return program
    name = os.path.basename(program).lower()
    find = codex if name.startswith("codex") else claude_code if name.startswith("claude") else None
    return (find and find()) or program


def runs(program):
    """Whether a program is a file this account can run."""
    return os.path.isfile(program) and os.access(program, os.X_OK)


def starter():
    return dict(config.STARTER, profiles={k: dict(v) for k, v in config.STARTER["profiles"].items()})


def read(path=None):
    path = path or config.default_path()
    if not path.is_file():
        return starter()
    return json.loads(path.read_text(encoding="utf-8-sig"))


def loaded(path=None):
    """(the config as the window edits it, None), or (the starter, why the file does not read)."""
    path = path or config.default_path()
    try:
        data = read(path)
    except (OSError, ValueError) as exc:
        return starter(), "%s does not read: %s" % (path.name, exc)
    if not (isinstance(data, dict) and isinstance(data.get("profiles"), dict) and data["profiles"]
            and all(isinstance(each, dict) for each in data["profiles"].values())
            and isinstance(data.get("profile", ""), str)):
        return starter(), '%s needs a "profiles" object of profiles' % path.name
    return data, None


def in_use(data):
    return data.get("profile") or next(iter(data["profiles"]), None)


def unreadable(path, data):
    """Why the profile in use, or one the window switches to, does not read; None when they all do."""
    name = in_use(data)
    for each in [name] + [other for other in CHOICES if other in data["profiles"] and other != name]:
        try:
            config.resolve(path, each)
        except (OSError, ValueError) as exc:
            return config.plainly(exc)
    return None


def key_state():
    """Where Claude's credential comes from (keys.claude_credential), or "missing"."""
    return keys.claude_credential()[0] or "missing"


def typed():
    from .service import typed
    return typed()


def state(path=None):
    """What the window shows. Never the key itself: only whether there is one, and where."""
    path = path or config.default_path()
    data, problem = loaded(path)  # a problem: the window shows the starter, and how to fix it
    locked = bool(problem)  # nothing the window changes can be used: the file comes first
    named = TEMPLATES["tones"]["named"]  # with the profile's own templates file's tones over them
    if not problem and path.is_file():
        try:
            from .modes import merged
            named = merged(config.resolve(path, in_use(data))[2])["tones"]["named"]
        except (OSError, ValueError) as exc:
            problem, locked = config.plainly(exc), True
        else:
            problem = unreadable(path, data)  # one the window switches to: only that choice fails
    profiles = data["profiles"]
    name = in_use(data)
    entry = profiles.get(name) or {}
    choice = name if name in CHOICES or name == "local" else "other"
    server = profiles.get("server") or config.STARTER["profiles"]["server"]
    url = server.get("model_url", "")
    models = server_models(url) if choice == "server" else []  # asked once: an address that does not answer waits 5 s
    # The model server the profile in use writes with, whatever its name ("local", one of your own).
    serving = entry.get("backend") in ("llama", "openai")
    in_use_url = entry.get("model_url") or config.DEFAULTS["model_url"]
    in_use_models = models if choice == "server" else server_models(in_use_url) if serving else []
    tone = entry.get("tone") or data.get("tone") or "corporate"  # the one in use: the profile's own, else the file's
    return {
        "profile": name, "choice": choice,
        "key": key_state(), "key_where": keys.where(), "key_env": keys.claude_credential()[1],
        "server": {"url": server.get("model_url", ""), "model": server.get("model") or "",
                   "key": "saved" if keys.server_key(server.get("model_url", "")) else "missing",
                   "key_where": keys.where(keys.server_name(server.get("model_url", "")))},
        "config_problem": problem,
        "config_locked": locked,
        "tone": tone, "own_words": tone not in named,
        "summon": (data.get("keys") if isinstance(data.get("keys"), dict) else {}).get("summon", config.SUMMON_KEYS[0]),
        "hints": data.get("hints", True) is not False,
        "tones": [{"name": n, "about": t.get("about", "")} for n, t in named.items()],
        "config": str(path),
        # The server cd_AI writes with must answer, or "Ready" would be a lie (a refused
        # connection on this computer answers at once).
        "server_problem": server_problem(in_use_url, in_use_models, entry.get("model")) if serving else None,
        "model": entry.get("model") or "",  # the profile in use's
        "server_models": models if isinstance(models, list) else [],
        "claude_code": None if claude_code() else NO_CLAUDE_CODE,  # what the Claude Code choice would say
        "codex": None if codex() else NO_CODEX,
        "command": (entry.get("command") or [None])[0] if choice in ("claude-code", "codex") else None,
        "claudish": typed(),  # how the page names claudish's commands here
    }


def check_key(key):
    """None when Anthropic accepts the key (a model listing: free, no text sent), else why not."""
    try:
        import anthropic
    except ImportError:
        from .doctor import SDK_INSTALL
        return "the Anthropic SDK is missing from this install: run `%s` in cd_AI's checkout" % SDK_INSTALL
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
KEY_CHARACTERS = "key characters"  # server_models: the key has characters an HTTP header cannot carry
NOT_MODELS = "not models"  # server_models: it answered, but not with a model list


def server_models(url, key=None):
    """The models an OpenAI-compatible server at url has, LOADING while it is still loading one
    (llama.cpp answers 503 then), the HTTP status of another refusal, NOT_MODELS for an answer that
    is not a model list, KEY_CHARACTERS for a key a header cannot carry, or None when nothing answers
    there. key: its API key, if any (by default the one saved for this address)."""
    from urllib.error import HTTPError
    from urllib.request import Request
    from .model import opener_for
    key = key or keys.server_key(url)
    headers = {"Authorization": "Bearer " + key} if key else {}
    try:
        (key or "").encode("latin-1")  # what an HTTP header can carry
    except UnicodeError:
        return KEY_CHARACTERS  # a pasted key with a character such as a non-breaking hyphen
    try:
        with opener_for(url).open(Request(url.rstrip("/") + "/v1/models", headers=headers),
                                  timeout=5) as response:
            body = response.read(4 << 20)
    except HTTPError as exc:
        return LOADING if exc.code == 503 else UNAUTHORIZED if exc.code in (401, 403) else exc.code
    except Exception:  # nothing there, or an address that cannot be asked
        return None
    try:  # it answered: a model list, or something else (a web page)
        from .model import model_ids
        return model_ids(json.loads(body))
    except ValueError:
        return NOT_MODELS


def listed(url, key=None):
    """The server's models, or none while it loads or when nothing answers."""
    models = server_models(url, key)
    return models if isinstance(models, list) else []


def check_server(url, model=None, key=None):
    """None when the server answers at url and has the model (or names none), else why not."""
    return server_problem(url, server_models(url, key), model, key)


def server_problem(url, models, model=None, key=None):
    """check_server for a listing already asked for (server_models)."""
    if models is None:
        return "nothing answers at %s" % url
    if models == UNAUTHORIZED:
        return "%s wants an API key, and did not accept this one" % url if key or keys.server_key(url) \
            else "%s wants an API key" % url
    if isinstance(models, int) and not isinstance(models, bool):
        hint = " (cd_AI adds /v1 itself: the address without it)" if url.rstrip("/").endswith("/v1") else ""
        return "%s answered %d to %s/v1/models%s" % (url, models, url.rstrip("/"), hint)
    if models == LOADING:
        return "the server at %s is still loading its model: try again in a moment" % url
    if models == KEY_CHARACTERS:
        return "the key has a character that is not a plain letter, digit or symbol: paste it again"
    if models == NOT_MODELS:
        return "%s answered, but not with a list of models at %s/v1/models" % (url, url.rstrip("/"))
    if model and models and model not in models:
        return "the server has no model %r; it has: %s" % (model, ", ".join(models))
    if not model and isinstance(models, list) and len(models) > 1:  # which one would be a guess: every request fails
        return "the server has several models (%s): pick one" % ", ".join(models[:8])
    return None


def accepted_key(key):
    """The key, whole and accepted by Anthropic, or ValueError saying why not."""
    if not isinstance(key, str) or not key.strip() or len(key) > 400 or any(c.isspace() for c in key.strip()):
        raise ValueError("paste the whole key, without spaces")
    problem = check_key(key.strip())
    if problem:
        raise ValueError(problem)
    return key.strip()


def apply(changes, path=None):
    """Make the window's changes; ValueError (with words for the window) when one is not valid.
    The key is checked before it is saved, and a key Anthropic refuses is not saved."""
    if not isinstance(changes, dict) or not set(changes) <= {"choice", "key", "server", "tone", "summon", "hints"}:
        raise ValueError("unknown setting")
    path = path or config.default_path()
    before = path.stat().st_mtime_ns if path.is_file() else None
    try:
        data = read(path)
    except ValueError as exc:  # edited by hand, and it does not read: where, and how to fix it
        raise ValueError("%s does not read (%s): fix it (it applies when you save), or move it aside" % (path, exc))
    profiles = data.setdefault("profiles", {})
    if "key" in changes:
        changes = dict(changes, key=accepted_key(changes["key"]))
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
        entry = profiles.setdefault("server", dict(config.STARTER["profiles"]["server"]))
        entry.update(model_url=url.strip().rstrip("/"), model=model.strip())
    if "choice" in changes and not (isinstance(changes["choice"], str) and changes["choice"] in CHOICES):
        raise ValueError("unknown choice")
    if changes.get("choice") == "server" or ("server" in changes and in_use(data) == "server"):
        server = profiles.get("server") or config.STARTER["profiles"]["server"]
        problem = check_server(server["model_url"], server.get("model"), server_key if "server" in changes else None)
        if problem:  # switching to a server that is not there would leave every rewrite failing
            raise ValueError(problem)
    for choice, find, missing in (("claude-code", claude_code, NO_CLAUDE_CODE), ("codex", codex, NO_CODEX)):
        if changes.get("choice") == choice:
            entry = profiles.setdefault(choice, dict(config.STARTER["profiles"][choice]))
            kept = entry.get("command")
            if isinstance(kept, list) and kept and isinstance(kept[0], str) and runs(os.path.expanduser(kept[0])):
                entry["backend"] = choice  # the profile's own command (a path, a wrapper with arguments) runs as it is
                continue
            command = find()
            if not command:  # like a server that is not there: no switch to a model that cannot answer
                raise ValueError(missing)
            # Kept running beside the service (claudish/warm.py); the full path, so the login service
            # finds it without the shell's PATH. Keep the profile's model, tone and other settings.
            entry.update(backend=choice, command=[command])
    if "choice" in changes:
        name = CHOICES[changes["choice"]]
        profiles.setdefault(name, dict(config.STARTER["profiles"][name]))
        data["profile"] = name
    if "tone" in changes:
        tone = changes["tone"]
        if not isinstance(tone, str) or len(tone) > 200 or "\n" in tone:
            raise ValueError("a tone is a name or a few words")
        config.set_tone(data, tone, in_use(data))
    if "summon" in changes:  # which key asks the model; the other keeps your words
        if changes["summon"] not in config.SUMMON_KEYS:
            raise ValueError("the key that asks is Shift+Enter or Enter")
        data.pop("keys", None)
        if changes["summon"] != config.SUMMON_KEYS[0]:
            data["keys"] = {"summon": changes["summon"]}
    if "hints" in changes:  # key hints and toasts; off: the panel only while something is pending
        if not isinstance(changes["hints"], bool):
            raise ValueError("hints are on or off")
        data.pop("hints", None)
        if not changes["hints"]:
            data["hints"] = False
    # The checks take seconds (a server, Anthropic): a hand edit meanwhile is not written over.
    if (path.stat().st_mtime_ns if path.is_file() else None) != before:
        raise ValueError("config.json changed while this was being saved (an edit by hand?): nothing was saved, try again")
    if "server" in changes and server_key:  # accepted by the server: saved for its address only
        keys.store(server_key, keys.server_name(profiles["server"]["model_url"]))
    if "key" in changes:  # saved once everything else is accepted
        keys.store(changes["key"])
    if set(changes) - {"key"} or not path.is_file():
        config.save(data, path)
    return state(path)
