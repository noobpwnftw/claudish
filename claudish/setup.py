"""`claudish setup`: from a fresh checkout to typing, in one command.

Each step checks first and does nothing when it is already done. A step that changes
anything runs only after a yes (or with --yes); --dry-run only shows the plan. Steps
that need an administrator (Windows, macOS input methods) print the exact command.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from . import config, doctor, mcp_setup, service

ROOT = Path(__file__).resolve().parents[1]


def scripts():
    """scripts/ holds the download helpers; they are standalone files, not a package."""
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    import download_llama
    import download_model
    return download_llama, download_model


def chosen_profile(profile):
    """(name, settings) of the profile setup is for, from the config or (before it exists) the starter."""
    if config.default_path().is_file():
        name, settings, _, _ = config.resolve(profile=profile)
        return name, settings
    name = profile or config.STARTER["profile"]
    if name not in config.STARTER["profiles"]:
        raise ValueError("profile %r is not a starter profile (have: %s)" % (name, ", ".join(config.STARTER["profiles"])))
    return name, dict(config.DEFAULTS, **config.STARTER["profiles"][name])


def progress(label):
    if not sys.stderr.isatty():
        return None
    return lambda received, total: sys.stderr.write("\r  %s: %d/%d MB" % (label, received >> 20, total >> 20))


def step_config():
    path = config.default_path()
    if path.is_file():
        return "done", str(path), None
    return "todo", "write %s with profiles: %s" % (path, ", ".join(config.STARTER["profiles"])), config.write_starter


def step_mcp():
    found = mcp_setup.discover()
    if not found:
        return "skip", "no MCP servers configured for Claude Desktop or Claude Code", None
    path = config.default_path()
    have = (json.loads(path.read_text(encoding="utf-8")).get("mcp_servers") or {}) if path.is_file() else {}
    new = sorted(set(found) - set(have))
    if not new:
        return "done", "all %d already imported" % len(found), None
    return "todo", "import %s from your Claude setup (secrets become $VARIABLES)" % ", ".join(new), \
        lambda: mcp_setup.import_servers()


def step_llama(settings, variant):
    download_llama, _ = scripts()
    found = (shutil.which("llama-server") or download_llama.installed()
             or next(iter((ROOT / ".tools/build/bin").glob("llama-server*")), None))
    if found:
        return "done", str(found), None
    asset = download_llama.ASSETS.get(download_llama.host() + (variant,))
    if asset is None:
        return "manual", "no pinned %s build for %s %s" % ((variant,) + download_llama.host()), \
            "get llama-server from https://github.com/ggml-org/llama.cpp/releases and put it on PATH"
    return "todo", "download llama.cpp %s (%s, %d MB, SHA-256 verified) into .tools/" % (
        download_llama.BUILD, asset[0], asset[1] >> 20), \
        lambda: download_llama.install(variant, progress("llama.cpp"))


def step_model():
    _, download_model = scripts()
    if download_model.target("small").is_file():
        return "done", str(download_model.target("small")), None
    size = download_model.PRESETS["small"][3]
    return "todo", "download Qwen2.5 0.5B (%d MB, SHA-256 verified) into models/" % (size >> 20), \
        lambda: download_model.fetch("small", progress("model"))


def step_ime():
    system = platform.system()
    if system == "Linux":
        results = doctor.check_ime_linux()
        first = results[0]
        if first[1] == "ok":
            return "done", first[2], None
        if "not installed" in first[2]:
            return "manual", first[2], first[3]
        command = ["/usr/bin/python3", str(ROOT / "platforms/linux/install.py")]
        return "todo", "register the IBus engine for this user (takes effect at your next login)", \
            lambda: subprocess.run(command, check=True)
    results = (doctor.check_ime_windows() if system == "Windows" else
               doctor.check_ime_macos() if system == "Darwin" else [])
    problems = [r for r in results if r[1] == "fail"]
    if not results:
        return "skip", "no input method for %s" % system, None
    if not problems:
        return "done", "; ".join(r[2] for r in results), None
    return "manual", problems[0][2], "; then ".join(r[3] for r in problems if r[3])


def step_service(name, settings):
    status, detail = service.managed()
    if status == "ok":
        return "done", detail, None
    if status == "skip":
        return "skip", detail, None
    try:
        doctor.fetch_json(doctor.SERVICE + "/health")
        return "manual", "a Claudish service is already running outside the service manager", \
            "stop it (Ctrl+C in its terminal), then run setup again"
    except Exception:
        pass
    local = settings["backend"] == "llama" and urlsplit(settings["model_url"]).hostname in ("127.0.0.1", "localhost")
    extra = [] if name in (None, "local") else ["--profile", name]
    what = "the local model and service" if local else "`claudish serve --profile %s`" % name
    if settings.get("api_key_env"):
        what += "; it will need %s in the service manager's environment, not just your shell" % settings["api_key_env"]
    return "todo", "start %s at every login" % what, lambda: service.run("install", serve=not local, extra=extra)


def plan(profile=None, variant="cpu", skip=()):
    """[(name, state, detail, action)]: state is done, todo, manual (action is the instruction), or skip."""
    name, settings = chosen_profile(profile)
    local = settings["backend"] == "llama" and urlsplit(settings["model_url"]).hostname in ("127.0.0.1", "localhost")
    steps = [("Config", step_config), ("MCP servers", step_mcp)]
    if local:
        steps += [("llama.cpp", lambda: step_llama(settings, variant)), ("Model", step_model)]
    steps += [("Input method", step_ime), ("Starts at login", lambda: step_service(name, settings))]
    return name, [(label, "skip", "skipped (--skip)", None) if label.split()[0].lower() in skip
                  else (label,) + check() for label, check in steps]


WAIT = 60


def wait_for_service(seconds=WAIT):
    """A newly started service loads its model first; give it time before doctor looks."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            doctor.fetch_json(doctor.SERVICE + "/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def ask(question):
    try:
        return input(question + " [Y/n] ").strip().lower() in ("", "y", "yes")
    except EOFError:
        return False


def run(profile=None, yes=False, dry_run=False, variant="cpu", skip=()):
    try:
        name, steps = plan(profile, variant, skip)
    except ValueError as exc:
        print("setup: %s" % exc)
        return 2
    symbols = doctor.marks()
    shown = {"done": symbols["ok"], "todo": "→" if symbols is doctor.MARKS else "->",
             "manual": symbols["warn"], "skip": symbols["skip"]}
    print("Setting up Claudish for profile %r.\n" % (name or "local"))
    manual, started, missing = [], False, []
    for label, state, detail, action in steps:
        print("%s %-16s %s" % (shown[state], label, detail))
        if state == "manual":
            manual.append((label, action))
            missing.append(label)
        if state != "todo" or dry_run:
            continue
        if label == "Starts at login" and set(missing) & {"llama.cpp", "Model"}:
            # A login service without its model would only fail at every login.
            print("  not yet: the local model needs %s first" % " and ".join(m for m in missing if m in ("llama.cpp", "Model")))
            continue
        if not (yes or ask("  %s?" % detail[0].upper() + detail[1:])):
            print("  skipped")
            missing.append(label)
            continue
        try:
            action()
        except (OSError, ValueError, subprocess.CalledProcessError, SystemExit) as exc:
            print("\n  failed: %s" % exc)
            manual.append((label, "fix the error above, then run `claudish setup` again"))
            missing.append(label)
            continue
        print("  done")
        started = started or label == "Starts at login"
    if dry_run:
        print("\nDry run: nothing was changed.")
        return 0
    for label, instruction in manual:
        print("\n%s needs you: %s" % (label, instruction))
    if started and not wait_for_service():
        print("\nThe service has not answered within %d seconds; doctor may report it as down." % WAIT)
    print("\nChecking the whole chain (claudish doctor):\n")
    status = doctor.main()
    if platform.system() == "Linux" and any(label == "Input method" and state == "todo" for label, state, _, _ in steps):
        print("\nLog out and back in, then add English → cd_AI — Claudish in your input sources.")
    return status
