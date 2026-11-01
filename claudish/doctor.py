"""`claudish doctor`: check the whole chain, from model to input method, and say how to fix each problem.

Each check returns (status, detail, fix): "ok", "warn" (works, but not as intended), "fail" (broken),
or "skip" (not applicable here).
"""
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
INSTALL_PY = ROOT / "platforms/linux/install.py"  # the full path: these fixes run from anywhere
SERVICE = "http://127.0.0.1:18765"


def fetch_json(url, timeout=2, key=None):
    opener = build_opener(ProxyHandler({})) if urlsplit(url).hostname in ("127.0.0.1", "localhost") else build_opener()
    request = Request(url, headers={"Authorization": "Bearer " + key} if key else {})
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


def check_python():
    if sys.version_info >= (3, 10):
        return "ok", "Python %s" % platform.python_version(), None
    return "fail", "Python %s" % platform.python_version(), "install Python 3.10 or newer"


def check_config(state):
    from . import config
    path = config.default_path()
    try:
        name, settings, _, context = config.resolve()
    except (OSError, ValueError) as exc:
        return "fail", str(exc), "fix %s, or move it aside and run `claudish init`" % path
    state.update(profile=name, settings=settings, context=context)
    if name is None:
        return "warn", "no config file: no model is set up", "`claudish setup` (Claude by default), or `claudish init` for example profiles"
    return "ok", "profile %r (backend %s) from %s" % (name, settings["backend"], path), None


def check_backend(state):
    settings = state.get("settings")
    if settings is None:
        return "skip", "config did not load", None
    backend = settings["backend"]
    if backend == "none":
        return "warn", "no model is set up: compose says so, continue only types", \
            "`claudish setup` (Claude by default), or a profile for any OpenAI-compatible server (docs/configuration.md)"
    if backend == "rules":
        return "ok", "rules backend (no model)", None
    if backend == "claude":
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return "fail", "the Anthropic SDK is not installed", SDK_FIX
        from .keys import claude_credential
        if not claude_credential()[0]:
            from .settings import claude_code, codex
            fix = "save one in cd_AI's settings (`claudish settings`) or with `claudish key`, or set ANTHROPIC_API_KEY, or run `ant auth login`"
            if codex():  # a ChatGPT subscription works through it, without an API key
                fix = "with a ChatGPT subscription, pick Codex in cd_AI's settings (`claudish settings`); or " + fix
            if claude_code():  # a Claude subscription works through it, without an API key
                fix = "with a Claude subscription, pick Claude Code in cd_AI's settings (`claudish settings`); or " + fix
            return "warn", "no Claude key: none saved, no ANTHROPIC_API_KEY, no `ant auth login` profile", fix
        from .model import CLAUDE_MODEL
        return "ok", "Claude via the Anthropic SDK (%s)" % (settings.get("model") or CLAUDE_MODEL), None
    if backend in ("claude-code", "codex"):
        name, find = ("Claude Code", "claude") if backend == "claude-code" else ("Codex", "codex")
        program = settings["command"][0]
        if shutil.which(program) or Path(program).is_file():
            from .warm import ClaudeCode, Codex
            model = settings.get("model") or (ClaudeCode if backend == "claude-code" else Codex).default_model
            return "ok", "%s (%s), kept running by the service" % (name, model), None
        from . import settings as window
        found = window.claude_code() if backend == "claude-code" else window.codex()
        if found:  # an update moved it: the service finds it again; saving the choice records the new path
            return "ok", "%s at %s, kept running by the service" % (name, found), None
        return "fail", "%s's `%s` command was not found" % (name, find), \
            "install %s and log in, then pick it again in cd_AI's settings (`claudish settings`)" % name
    if backend == "command":
        program = settings["command"][0]
        if shutil.which(program) or Path(program).is_file():
            return "ok", "agent command %s" % program, None
        return "fail", "agent command %r not found" % program, "install it, or give its full path in the profile's \"command\""
    url = settings["model_url"]
    from .keys import for_profile
    key = for_profile(settings)  # what the service sends
    try:
        listing = fetch_json(url.rstrip("/") + ("/health" if backend == "llama" else "/v1/models"), key=key)
        if backend == "openai" and settings.get("model"):  # as the settings window checks it
            from .settings import server_problem
            names = [m.get("id") for m in (listing or {}).get("data", []) if isinstance(m, dict)]
            problem = server_problem(url, names, settings["model"], key)
            if problem:
                return "fail", problem, "name one of its models in the profile's \"model\", or pick it in cd_AI's settings"
        return "ok", "model server reachable at %s" % url, None
    except HTTPError as exc:
        if exc.code == 503:
            return "warn", "the model server at %s is still loading its model" % url, "wait a moment, then check again"
        if exc.code in (401, 403):
            return "fail", "the model server at %s did not accept the key" % url, \
                "save its key in cd_AI's settings (`claudish settings`)"
        return "fail", "the model server at %s answered %d" % (url, exc.code), \
            "start your model server, or fix the profile's model_url"
    except Exception as exc:
        fix = ("`claudish setup --profile local` downloads llama.cpp and the model if they are missing, and "
               "puts the server in the profile's \"command\", which the service runs" if backend == "llama"
               else "start your model server, or fix the profile's model_url")
        return "fail", "no model server at %s (%s)" % (url, type(exc).__name__), fix


def check_service():
    try:
        health = fetch_json(SERVICE + "/health")
    except Exception:
        return "fail", "the Claudish service is not running at %s" % SERVICE, \
            "start it at every login: `claudish service install` (it runs the config's profile)"
    if not ours():
        return "fail", "another account's cd_AI service has %s" % SERVICE, \
            "one account at a time can use it: log the other account out, or stop its service there"
    detail = "running: backend %s, profile %s" % (health.get("backend"), health.get("profile"))
    model = health.get("model")  # Claude Code, Codex or a local model, kept running beside the service
    if model and model.startswith("failed"):
        fix = ("run the profile's \"command\" (llama-server) in a terminal to see why it stops"
               if health.get("backend") == "llama" else
               "check that its CLI works and is logged in (`claude` or `codex` in a terminal), then `claudish service install`")
        return "fail", "%s; its model process %s" % (detail, model), fix
    if model in ("starting", "restarting"):
        return "warn", "%s; its model process is %s" % (detail, model), "wait a few seconds and check again"
    return "ok", detail + ("; its model process is warm" if model == "warm" else ""), None


def ours():
    """Whether the service answering is this account's: it takes this account's token."""
    from urllib.error import HTTPError
    from .client import settings_url
    try:
        settings_url(SERVICE)
        return True
    except HTTPError as exc:
        return exc.code != 403
    except OSError:
        return True  # it did not answer this time: not another account's, as far as we know


def check_managed():
    from . import service
    status, detail = service.managed()
    return status, detail, "`claudish service install` (it runs the config's profile)" \
        if status == "warn" else None


def check_ime_linux():
    if not shutil.which("ibus-daemon"):
        return [("Input method", "fail", "IBus is not installed", "sudo apt install ibus python3-gi gir1.2-ibus-1.0")]
    results = []
    user = Path.home() / ".local/share/ibus/component/claudish.xml"
    system = Path("/usr/share/ibus/component/claudish.xml")
    component = user if user.is_file() else system if system.is_file() else None
    if component is None:
        return [("Input method", "fail", "the Claudish IBus component is not registered",
                 "/usr/bin/python3 %s   (then log out and back in)" % INSTALL_PY)]
    text = component.read_text(encoding="utf-8", errors="replace")
    engine = text.split('&quot;')[1] if '&quot;' in text else ""
    if engine and not Path(engine).is_file():
        results.append(("Input method", "fail", "the registered engine %s no longer exists (moved checkout?)" % engine,
                        "/usr/bin/python3 %s" % INSTALL_PY))
    else:
        results.append(("Input method", "ok", "registered (%s)" % component, None))
    if component == user:
        path = os.environ.get("IBUS_COMPONENT_PATH", "")
        if str(user.parent) not in path.split(":"):
            environment = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "environment.d/90-claudish-ibus.conf"
            if environment.is_file():  # set up; this session started before it, as any new install's does
                results.append(("IBus search path", "warn",
                                "set up in %s; it takes effect at your next login" % environment,
                                "log out and back in; if your session ignores environment.d: "
                                "sudo /usr/bin/python3 %s --system" % INSTALL_PY))
            else:
                results.append(("IBus search path", "fail",
                                "this session's IBUS_COMPONENT_PATH does not include %s, so IBus cannot see Claudish" % user.parent,
                                "/usr/bin/python3 %s, then log out and back in" % INSTALL_PY))
        else:
            results.append(("IBus search path", "ok", "includes the user component directory", None))
    try:
        engines = subprocess.run(["ibus", "list-engine"], capture_output=True, text=True, timeout=5).stdout
        if "claudish" in engines:
            results.append(("IBus engine", "ok", "IBus lists Claudish", None))
        else:
            results.append(("IBus engine", "warn", "the running IBus does not list Claudish yet",
                            "log out and back in, or run `ibus restart` in a session with the search path set"))
    except (OSError, subprocess.TimeoutExpired):
        results.append(("IBus engine", "skip", "IBus is not running in this session", None))
    return results


def windows_pime():
    """cd_AI's PIME: beside the Python running this (the installer's <app>\\python and <app>\\PIME),
    else where the installer puts it."""
    beside = Path(sys.executable).resolve().parent.parent / "PIME"
    if beside.is_dir():
        return beside
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "cd_AI" / "PIME"


def check_ime_windows():
    pime = windows_pime()
    if not (pime / "python" / "input_methods" / "claudish").is_dir():
        return [("Input method", "fail", "cd_AI's input method is not installed",
                 "install it with cd_AI-setup.exe (docs/install.md#windows-input-method)")]
    results = [("Input method", "ok", "installed in %s" % pime, None)]
    # cd_AI's launcher serves its own pipe (\\.\pipe\<user>\cd_AI\Launcher), beside any PIME's.
    try:
        pipes = os.listdir("\\\\.\\pipe\\")
    except OSError:
        pipes = []
    if any(name.endswith("cd_AI\\Launcher") for name in pipes):
        results.append(("Launcher", "ok", "serving its pipe", None))
    else:
        results.append(("Launcher", "fail", "cd_AI's launcher is not running",
                        "start \"%s\" or sign out and back in" % (pime / "PIMELauncher.exe")))
    return results


# Every installer has it; a checkout installs it into its venv.
SDK_FIX = '%s -m pip install -e ".[claude]" in the checkout' % sys.executable


def check_ime_macos():
    bundle = Path.home() / "Library/Input Methods/Claudish.app"
    if bundle.is_dir():
        return [("Input method", "ok", "installed (%s)" % bundle, None)]
    return [("Input method", "fail", "Claudish.app is not installed",
             "install cd_AI.pkg again (in a checkout: python3 platforms/macos/build.py --install), then log out and back in")]


def check_context(state):
    context, settings = state.get("context"), state.get("settings") or {}
    providers = list(context.providers) if context else []
    bindings = settings.get("bindings") or []
    if not providers and not bindings:
        return [("Context", "skip", "no context providers or bindings configured", None)]
    results = []
    for label, provider in [("profile", p) for p in providers] + \
                           [("app %s" % b.pattern, p) for b in bindings for p in b.providers]:
        text = provider.get()
        name = "Context: %s" % provider.name
        if text is None:
            results.append((name, "fail", "%s provider failed: %s" % (label, getattr(provider, "error", "no text")),
                            "check its command, URL, or MCP server; run it by hand to see the error"))
        else:
            results.append((name, "ok", "%s provider returned %d characters" % (label, len(text)), None))
    return results


def run():
    state, results = {}, []
    for name, check in [("Python", check_python), ("Config", lambda: check_config(state)),
                        ("Backend", lambda: check_backend(state)), ("Service", check_service),
                        ("Starts at login", check_managed)]:
        results.append((name,) + check())
    system = platform.system()
    results += (check_ime_linux() if system == "Linux" else check_ime_windows() if system == "Windows"
                else check_ime_macos() if system == "Darwin" else [("Input method", "skip", system, None)])
    results += check_context(state)
    return results


MARKS = {"ok": "✓", "warn": "!", "fail": "✗", "skip": "-"}


def marks():
    """Symbols where the console can show them; ASCII on, for example, a cp1252 Windows console."""
    try:
        "".join(MARKS.values()).encode(sys.stdout.encoding or "ascii")
        return MARKS
    except (UnicodeEncodeError, LookupError):
        return {"ok": "[ok]", "warn": "[!]", "fail": "[x]", "skip": "[-]"}


def main(as_json=False):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a diagnostic tool must never die on its own output
    symbols = marks()
    from .service import as_typed
    results = [(n, s, d, as_typed(f) if f else f) for n, s, d, f in run()]
    if as_json:
        print(json.dumps([{"check": n, "status": s, "detail": d, "fix": f} for n, s, d, f in results], indent=1))
    else:
        for name, status, detail, fix in results:
            print("%s %-18s %s" % (symbols[status], name, detail))
            if fix and status in ("fail", "warn"):
                print("  %-18s fix: %s" % ("", fix))
    return 1 if any(status == "fail" for _, status, _, _ in results) else 0
