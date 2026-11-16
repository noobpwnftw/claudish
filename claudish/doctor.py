"""`claudish doctor`: check the whole chain, from model to input method, and say how to fix each problem.

Each check returns (status, detail, fix): "ok", "warn" (works, but not as intended), "fail" (broken),
or "skip" (not applicable here).
"""
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
INSTALL_PY = ROOT / "platforms/linux/install.py"  # the full path: these fixes run from anywhere
from .client import SERVICE  # noqa: E402
from .model import opener_for  # noqa: E402


def fetch_json(url, timeout=2, key=None):
    opener = opener_for(url)
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
        name, settings, templates, context = config.resolve()
        import contextlib, io
        from .model import Rewriter
        with contextlib.redirect_stderr(io.StringIO()):  # a missing key is the Model row's
            Rewriter.from_settings(settings, templates, context, name)  # as the service builds it ("tools" it cannot call)
    except ImportError:
        pass  # the Anthropic SDK: the Model row says so
    except (OSError, ValueError) as exc:
        return "fail", str(exc), "fix %s, or move it aside and run `claudish init`" % path
    state.update(profile=name, settings=settings, context=context)
    if name is None:
        return "warn", "no config file: no model is set up", "`claudish setup` (Claude by default), or `claudish init` for example profiles"
    return "ok", "profile %r (backend %s) from %s" % (name, settings["backend"], path), None


def service_has_no_key():
    """True when cd_AI's running service answers that it has no Claude key."""
    try:
        return fetch_json(SERVICE + "/health").get("key") is False
    except Exception:  # not running: setup's service step says what it needs
        return False


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
        source, variable = claude_credential()
        if not source:
            from .settings import claude_code, codex
            fix = "save one in cd_AI's settings (`claudish settings`) or with `claudish key`, or set ANTHROPIC_API_KEY, or run `ant auth login`"
            if codex():  # a ChatGPT subscription works through it, without an API key
                fix = "with a ChatGPT subscription, pick Codex in cd_AI's settings (`claudish settings`); or " + fix
            if claude_code():  # a Claude subscription works through it, without an API key
                fix = "with a Claude subscription, pick Claude Code in cd_AI's settings (`claudish settings`); or " + fix
            return "warn", "no Claude key: none saved, no ANTHROPIC_API_KEY, no `ant auth login` profile", fix
        if source == "environment" and service_has_no_key():
            return "warn", "the Claude key is in %s here, and cd_AI's service does not have it" % variable, \
                "save it with `claudish key` (a variable exported in a terminal does not reach a service started at login)"
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
        (key or "").encode("latin-1")  # what an HTTP header can carry
    except UnicodeError:
        return "fail", "the key saved for %s has a character an HTTP header cannot carry" % url, \
            "paste the key again in cd_AI's settings (`claudish settings`)"
    try:
        listing = fetch_json(url.rstrip("/") + ("/health" if backend == "llama" else "/v1/models"), key=key)
        if backend == "openai":  # as the settings window checks it (no model: the server's only one)
            from .settings import server_problem
            from .model import model_ids
            try:
                names = model_ids(listing)
            except ValueError:
                names = []
            problem = server_problem(url, names, settings.get("model"), key)
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
        from . import service
        if platform.system() == "Linux" and not service.systemd_user():  # nothing to install it with
            return "fail", "the Claudish service is not running at %s" % SERVICE, service.NO_SYSTEMD
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


def ibus_packages():
    """How this distribution installs IBus and its Python bindings (/etc/os-release)."""
    known = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            known[key] = value.strip().strip('"')
    except OSError:
        pass
    family = (known.get("ID", "") + " " + known.get("ID_LIKE", "")).split()
    for names, command in ((("fedora", "rhel"), "sudo dnf install ibus python3-gobject"),
                           (("opensuse", "suse"), "sudo zypper install ibus python3-gobject"),
                           (("arch",), "sudo pacman -S ibus python-gobject")):
        if any(name in family for name in names) or any(each.startswith(names) for each in family):
            return command
    return "sudo apt install ibus python3-gi gir1.2-ibus-1.0"


def check_frameworks():
    """Apps send keys to the framework these name: another one (fcitx) gets them, not IBus. On
    Wayland, "wayland" (or none) sends them through the compositor, which hands them to IBus on GNOME
    and KDE; "xim" reaches IBus when XMODIFIERS names it."""
    wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE") == "wayland"
    xim = os.environ.get("XMODIFIERS") == "@im=ibus"
    modules = {"ibus"} | ({"wayland"} if wayland else set()) | ({"xim"} if xim else set())
    fine = {"GTK_IM_MODULE": modules, "QT_IM_MODULE": modules, "XMODIFIERS": {"@im=ibus"}}
    other = [("%s=%s" % (name, os.environ[name])) for name in fine
             if os.environ.get(name) and os.environ[name] not in fine[name]]
    if other:
        return [("Input framework", "fail", "apps send their keys to another input method (%s)" % ", ".join(other),
                 "pick IBus: `im-config -n ibus` (Ubuntu, Debian), or set these to ibus%s; then log out and back in"
                 % (" or remove them" if wayland else ""))]
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if wayland and desktop and not any(name in desktop for name in ("gnome", "kde")) \
            and not (os.environ.get("GTK_IM_MODULE") and os.environ.get("QT_IM_MODULE")):
        # wlroots compositors (Sway, Hyprland) speak input-method-v2, which IBus does not: apps reach
        # IBus only through its own GTK and Qt modules.
        return [("Input framework", "warn", "on %s, apps reach IBus only when GTK_IM_MODULE and QT_IM_MODULE are ibus"
                 % os.environ["XDG_CURRENT_DESKTOP"],
                 "add GTK_IM_MODULE=ibus and QT_IM_MODULE=ibus to ~/.config/environment.d/ (or your compositor's "
                 "config); then log out and back in")]
    return []


def ibus_started():
    """When this user's ibus-daemon started (seconds since the epoch), or None."""
    try:
        pid = subprocess.run(["pgrep", "-u", str(os.getuid()), "-x", "ibus-daemon"], capture_output=True,
                             text=True, timeout=5).stdout.split()[0]
        ticks = int(Path("/proc/%s/stat" % pid).read_text().rsplit(")", 1)[1].split()[19])
        boot = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                    if line.startswith("btime "))
        return boot + ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, IndexError, ValueError, StopIteration, subprocess.TimeoutExpired):
        return None


GNOME_SOURCES = "Settings → Keyboard → Input Sources"  # where GNOME lists input methods
IBUS_SOURCES = "IBus Preferences (ibus-setup) → Input Method"  # where other desktops do (IBus's own)
ADD_ELSEWHERE = IBUS_SOURCES + " → Add → English → Claudish"


def where_to_add():
    """Where this desktop lists input methods: GNOME's Input Sources, else IBus's own."""
    if "gnome" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower():
        return GNOME_SOURCES
    return IBUS_SOURCES


def check_ibus_sources():
    """Other desktops (KDE, Xfce, Sway…): Claudish among IBus's own input methods, which its
    switch key and panel go through (GNOME keeps its own list: check_gnome)."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if not desktop or "gnome" in desktop or not shutil.which("gsettings"):
        return []
    try:
        engines = subprocess.run(["gsettings", "get", "org.freedesktop.ibus.general", "preload-engines"],
                                 capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if engines.returncode:
        return []
    if "'claudish'" in engines.stdout:
        return [("Input source", "ok", "Claudish is among IBus's input methods", None)]
    return [("Input source", "warn", "Claudish is not among IBus's input methods", ADD_ELSEWHERE)]


def check_gnome():
    """GNOME: Claudish among the input sources, and its Shell extension running (it draws the panel
    and tells the engine which window has focus)."""
    if "gnome" not in os.environ.get("XDG_CURRENT_DESKTOP", "").lower() or not shutil.which("gsettings"):
        return []
    results = []
    try:
        sources = subprocess.run(["gsettings", "get", "org.gnome.desktop.input-sources", "sources"],
                                 capture_output=True, text=True, timeout=5).stdout
        if "'claudish'" not in sources:
            results.append(("Input source", "warn", "Claudish is not among your input sources",
                            GNOME_SOURCES + " → + → English → Claudish"))
        else:
            results.append(("Input source", "ok", "Claudish is an input source", None))
        info = subprocess.run(["gnome-extensions", "info", "cd-ai@claudish.io"], capture_output=True, text=True,
                              timeout=5).stdout if shutil.which("gnome-extensions") else ""
        state = next((line.split(":", 1)[1].strip() for line in info.splitlines() if line.strip().startswith("State:")), "")
        if state.upper() in ("ACTIVE", "ENABLED"):
            results.append(("GNOME extension", "ok", "running", None))
        elif state:
            results.append(("GNOME extension", "warn", "its state is %s (it draws cd_AI's panel and says which window "
                            "has focus)" % state, "turn it on in Extensions; OUT OF DATE: this GNOME is newer than "
                            "cd_AI supports yet"))
    except (OSError, subprocess.TimeoutExpired):
        pass
    return results


def check_ime_linux():
    if not shutil.which("ibus-daemon"):
        return [("Input method", "fail", "IBus is not installed", ibus_packages())]
    results = check_frameworks()
    user = Path.home() / ".local/share/ibus/component/claudish.xml"
    system = Path("/usr/share/ibus/component/claudish.xml")
    component = user if user.is_file() else system if system.is_file() else None
    if component is None:
        return [("Input method", "fail", "the Claudish IBus component is not registered",
                 "/usr/bin/python3 %s   (then log out and back in)" % shlex.quote(str(INSTALL_PY)))]
    text = component.read_text(encoding="utf-8", errors="replace")
    from xml.sax.saxutils import unescape
    engine = unescape(text.split('&quot;')[1]) if '&quot;' in text else ""  # install.py escapes it (R&amp;D)
    if engine and not Path(engine).is_file():
        results.append(("Input method", "fail", "the registered engine %s no longer exists (moved checkout?)" % engine,
                        "/usr/bin/python3 %s" % shlex.quote(str(INSTALL_PY))))
    elif engine and Path(engine).resolve() != (INSTALL_PY.parent / "engine.py").resolve():
        # Another checkout's (a clone, then the one-line install): the input method would type with
        # that code while the service runs this one's.
        results.append(("Input method", "fail", "registered from another checkout: %s" % engine,
                        "/usr/bin/python3 %s   (then log out and back in)" % shlex.quote(str(INSTALL_PY))))
    else:
        results.append(("Input method", "ok", "registered (%s)" % component, None))
    if component == user and not system.is_file():  # (--system: IBus sees it anyway)
        path = os.environ.get("IBUS_COMPONENT_PATH", "")
        if str(user.parent) not in path.split(":"):
            environment = Path.home() / ".config/environment.d/90-claudish-ibus.conf"  # systemd's own folder (install.py)
            started = ibus_started()
            if environment.is_file() and started and started > environment.stat().st_mtime + 60:
                # IBus started after the file and still lacks it: this session does not read environment.d
                results.append(("IBus search path", "fail",
                                "this session does not read %s, so IBus cannot see Claudish" % environment,
                                "sudo /usr/bin/python3 %s --system, then log out and back in" % shlex.quote(str(INSTALL_PY))))
            elif environment.is_file():  # set up; this session started before it, as any new install's does
                results.append(("IBus search path", "warn",
                                "set up in %s; it takes effect at your next login" % environment,
                                "log out and back in; if your session ignores environment.d: "
                                "sudo /usr/bin/python3 %s --system" % shlex.quote(str(INSTALL_PY))))
            else:
                results.append(("IBus search path", "fail",
                                "this session's IBUS_COMPONENT_PATH does not include %s, so IBus cannot see Claudish" % user.parent,
                                "/usr/bin/python3 %s, then log out and back in" % shlex.quote(str(INSTALL_PY))))
        else:
            results.append(("IBus search path", "ok", "includes the user component directory", None))
    try:
        listed = subprocess.run(["ibus", "list-engine"], capture_output=True, text=True, timeout=5)
        engines = listed.stdout
        if listed.returncode:  # "Can't connect to IBus.": none in this session (SSH, a console)
            raise OSError(listed.stderr)
        if "claudish" in engines:
            results.append(("IBus engine", "ok", "IBus lists Claudish", None))
        else:
            results.append(("IBus engine", "warn", "the running IBus does not list Claudish yet",
                            "log out and back in, or run `ibus restart` in a session with the search path set"))
    except (OSError, subprocess.TimeoutExpired):
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):  # a desktop with no IBus: nothing types
            results.append(("IBus engine", "fail", "IBus is not running in this session",
                            "KDE: System Settings → Keyboard → Virtual Keyboard → IBus Wayland; elsewhere "
                            "`im-config -n ibus`, or start `ibus-daemon -drx` at login"))
        else:
            results.append(("IBus engine", "skip", "IBus is not running in this session", None))
        return results
    return results + check_gnome() + check_ibus_sources()


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
    # This account's (pipe names are machine-wide): the whole name, not a suffix (jimbob for bob).
    own = ("%s\\cd_AI\\Launcher" % os.environ.get("USERNAME", "")).lower()
    if os.environ.get("USERNAME") and any(name.lower() == own for name in pipes):
        results.append(("Launcher", "ok", "serving its pipe", None))
    else:
        results.append(("Launcher", "fail", "cd_AI's launcher is not running",
                        "Start-Process \"%s\" in PowerShell, or sign out and back in" % (pime / "PIMELauncher.exe")))
    return results


# Every installer has it; a checkout installs it into its venv.
SDK_INSTALL = '%s -m pip install -e ".[claude]"' % sys.executable  # in cd_AI's checkout
SDK_FIX = SDK_INSTALL + " in the checkout"


def macos_enabled():
    """Whether Text Input Sources has cd_AI enabled; None when it cannot be asked (a checkout's
    Python without the bundle's sources module)."""
    try:
        import sources  # the bundle's platforms/macos/sources.py
        return any(sources.prop(source, "kTISPropertyInputSourceIsEnabled")
                   for source in sources.sources("org.claudish.inputmethod.Claudish"))
    except Exception:
        return None


def check_ime_macos():
    bundle = Path.home() / "Library/Input Methods/Claudish.app"
    if bundle.is_dir():
        if macos_enabled() is False:  # installed, but not in Input Sources (Don't Allow, or removed there)
            return [("Input method", "fail", "installed, but not enabled in Text Input",
                     "`claudish register` (macOS asks to allow it), or System Settings → Keyboard → Text "
                     "Input → Edit → + → English → Claudish — Compose")]
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
    for label, provider in [("context", p) for p in providers] + \
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
