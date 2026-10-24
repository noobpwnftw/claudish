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
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
SERVICE = "http://127.0.0.1:18765"


def fetch_json(url, timeout=2):
    opener = build_opener(ProxyHandler({})) if urlsplit(url).hostname in ("127.0.0.1", "localhost") else build_opener()
    with opener.open(url, timeout=timeout) as response:
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
            "`claudish setup` (Claude with your own key), or a profile for any OpenAI-compatible server (docs/configuration.md)"
    if backend == "rules":
        return "ok", "rules backend (no model)", None
    if backend == "claude":
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return "fail", "the Anthropic SDK is not installed", 'pip install "claudish-ime[claude]"'
        from .keys import stored
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or stored()
                or Path.home().joinpath(".config", "anthropic").is_dir()):
            return "warn", "no Claude key: none saved, no ANTHROPIC_API_KEY, no `ant auth login` profile", \
                "save one in cd_AI's settings (`claudish settings`) or with `claudish key`, or set ANTHROPIC_API_KEY, or run `ant auth login`"
        return "ok", "Claude via the Anthropic SDK (%s)" % settings["claude_model"], None
    if backend == "command":
        program = settings["command"][0]
        if shutil.which(program) or Path(program).is_file():
            return "ok", "agent command %s" % program, None
        return "fail", "agent command %r not found" % program, "install it, or give its full path in the profile's \"command\""
    url = settings["model_url"]
    try:
        fetch_json(url.rstrip("/") + ("/health" if backend == "llama" else "/v1/models"))
        return "ok", "model server reachable at %s" % url, None
    except Exception as exc:
        fix = ("start it: `python scripts/start.py` (or `python scripts/run_model.py`)"
               if backend == "llama" else "start your model server, or fix the profile's model_url")
        if backend == "llama":
            if not list((ROOT / "models").glob("*.gguf")):
                fix = "download a model: `python scripts/download_model.py gemma`, then " + fix
            servers = list((ROOT / ".tools").glob("llama-*/llama-server*")) + list((ROOT / ".tools").glob("build/bin/llama-server*"))
            if not (servers or shutil.which("llama-server")):
                fix = "get llama.cpp: `python scripts/download_llama.py`; " + fix
        return "fail", "no model server at %s (%s)" % (url, type(exc).__name__), fix


def check_service(state):
    try:
        health = fetch_json(SERVICE + "/health")
    except Exception:
        return "fail", "the Claudish service is not running at %s" % SERVICE, \
            "start it: `python scripts/start.py` (local model) or `python -m claudish serve --profile NAME`"
    detail = "running: backend %s, profile %s" % (health.get("backend"), health.get("profile"))
    return "ok", detail, None


def check_managed():
    from . import service
    status, detail = service.managed()
    return status, detail, "claudish service install   (add -- --profile NAME for another profile, --local for the local model)" \
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
                 "/usr/bin/python3 platforms/linux/install.py   (then log out and back in)")]
    text = component.read_text(encoding="utf-8", errors="replace")
    engine = text.split('&quot;')[1] if '&quot;' in text else ""
    if engine and not Path(engine).is_file():
        results.append(("Input method", "fail", "the registered engine %s no longer exists (moved checkout?)" % engine,
                        "re-run platforms/linux/install.py from the current checkout"))
    else:
        results.append(("Input method", "ok", "registered (%s)" % component, None))
    if component == user:
        path = os.environ.get("IBUS_COMPONENT_PATH", "")
        if str(user.parent) not in path.split(":"):
            environment = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "environment.d/90-claudish-ibus.conf"
            results.append(("IBus search path", "fail",
                            "this session's IBUS_COMPONENT_PATH does not include %s, so IBus cannot see Claudish" % user.parent,
                            "log out and back in (installed: %s); if your session ignores environment.d: "
                            "sudo /usr/bin/python3 platforms/linux/install.py --system" % environment
                            if environment.is_file() else "re-run platforms/linux/install.py, then log out and back in"))
        else:
            results.append(("IBus search path", "ok", "includes the user component directory", None))
    try:
        engines = subprocess.run(["ibus", "list-engine"], capture_output=True, text=True, timeout=5).stdout
        if "claudish" in engines:
            results.append(("IBus engine", "ok", "IBus lists cd_AI — Claudish", None))
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


def check_ime_macos():
    bundle = Path.home() / "Library/Input Methods/Claudish.app"
    if bundle.is_dir():
        return [("Input method", "ok", "installed (%s)" % bundle, None)]
    return [("Input method", "fail", "Claudish.app is not installed",
             "python3 platforms/macos/build.py --install, then log out and back in")]


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
                        ("Backend", lambda: check_backend(state)), ("Service", lambda: check_service(state)),
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
    results = run()
    if as_json:
        print(json.dumps([{"check": n, "status": s, "detail": d, "fix": f} for n, s, d, f in results], indent=1))
    else:
        for name, status, detail, fix in results:
            print("%s %-18s %s" % (symbols[status], name, detail))
            if fix and status in ("fail", "warn"):
                print("  %-18s fix: %s" % ("", fix))
    return 1 if any(status == "fail" for _, status, _, _ in results) else 0
