"""`claudish service install|uninstall|status`: start the service at login, without a terminal.

Linux: a systemd user unit. Windows: a logon task (pythonw, no console). macOS: a launchd agent.
By default the local stack (scripts/start.py: model and service); with --serve, `claudish serve ARGS`.
"""
import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
NAME = "claudish"
LABEL = "com.claudish.service"


def command(serve, extra):
    """The argv the service manager runs."""
    if serve:
        return [sys.executable, str(ROOT / "scripts" / "serve.py")] + list(extra)
    return [sys.executable, str(ROOT / "scripts" / "start.py")] + list(extra)


def systemd_unit(argv):
    return """[Unit]
Description=Claudish input method service
After=default.target

[Service]
ExecStart=%s
WorkingDirectory=%s
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
""" % (" ".join(shlex.quote(part) for part in argv), ROOT)


def windows_task(argv):
    """schtasks arguments: pythonw instead of python, so no console window appears at login."""
    program = Path(argv[0])
    pythonw = program.with_name("pythonw.exe")
    argv = [str(pythonw if pythonw.is_file() else program)] + argv[1:]
    line = subprocess.list2cmdline(argv)
    return ["schtasks", "/create", "/tn", NAME, "/sc", "onlogon", "/rl", "limited", "/f", "/tr", line]


def launchd_plist(argv):
    arguments = "\n".join("    <string>%s</string>" % escape(part) for part in argv)
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>%s</string>
  <key>ProgramArguments</key>
  <array>
%s
  </array>
  <key>WorkingDirectory</key><string>%s</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
""" % (LABEL, arguments, escape(str(ROOT)))


def paths():
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return {"Linux": config / ("systemd/user/%s.service" % NAME),
            "Darwin": home / ("Library/LaunchAgents/%s.plist" % LABEL)}


def plan(action, serve=False, extra=()):
    """[(description, kind, payload)]: "write" (path, text), "run" (argv), or "remove" (path)."""
    system, argv = platform.system(), command(serve, extra)
    if system == "Linux":
        unit = paths()["Linux"]
        if action == "install":
            return [("write the systemd user unit", "write", (unit, systemd_unit(argv))),
                    ("reload systemd", "run", ["systemctl", "--user", "daemon-reload"]),
                    ("enable and start it", "run", ["systemctl", "--user", "enable", "--now", NAME])]
        if action == "uninstall":
            return [("stop and disable it", "run", ["systemctl", "--user", "disable", "--now", NAME]),
                    ("remove the unit", "remove", unit),
                    ("reload systemd", "run", ["systemctl", "--user", "daemon-reload"])]
        return [("status", "run", ["systemctl", "--user", "is-active", NAME])]
    if system == "Windows":
        if action == "install":
            return [("create the logon task", "run", windows_task(argv)),
                    ("start it now", "run", ["schtasks", "/run", "/tn", NAME])]
        if action == "uninstall":
            return [("stop it", "run", ["schtasks", "/end", "/tn", NAME]),
                    ("delete the logon task", "run", ["schtasks", "/delete", "/tn", NAME, "/f"])]
        return [("status", "run", ["schtasks", "/query", "/tn", NAME])]
    if system == "Darwin":
        agent, domain = paths()["Darwin"], "gui/%d" % os.getuid()
        if action == "install":
            return [("write the launch agent", "write", (agent, launchd_plist(argv))),
                    ("load it", "run", ["launchctl", "bootstrap", domain, str(agent)])]
        if action == "uninstall":
            return [("unload it", "run", ["launchctl", "bootout", "%s/%s" % (domain, LABEL)]),
                    ("remove the launch agent", "remove", agent)]
        return [("status", "run", ["launchctl", "print", "%s/%s" % (domain, LABEL)])]
    raise SystemExit("no service manager support for %s" % system)


def run(action, serve=False, extra=(), dry_run=False):
    steps = plan(action, serve, extra)
    for description, kind, payload in steps:
        if dry_run:
            shown = payload[0] if kind == "write" else payload if kind == "remove" else subprocess.list2cmdline(payload)
            print("would %s: %s" % (description, shown))
            if kind == "write":
                print(payload[1])
            continue
        if kind == "write":
            path, text = payload
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        elif kind == "remove":
            if payload.exists():
                payload.unlink()
        else:
            result = subprocess.run(payload, capture_output=True, text=True)
            if action == "status":
                print((result.stdout or result.stderr).strip() or ("active" if result.returncode == 0 else "inactive"))
                return result.returncode
            # Stopping something that is not running is fine during uninstall.
            if result.returncode != 0 and action != "uninstall":
                raise SystemExit("%s failed: %s" % (description, (result.stderr or result.stdout).strip()))
        print("%s: done" % description)
    if action == "install" and not dry_run:
        print("Claudish now starts at login. Check it with `claudish doctor`.")
    return 0


def managed():
    """(status, detail) for doctor: is the service registered with this OS's service manager?"""
    system = platform.system()
    try:
        if system == "Linux":
            if not paths()["Linux"].is_file():
                return "warn", "not managed: it will not start at login"
            state = subprocess.run(["systemctl", "--user", "is-active", NAME], capture_output=True, text=True,
                                   timeout=5).stdout.strip()
            return ("ok" if state == "active" else "warn"), "systemd user unit (%s)" % (state or "unknown")
        if system == "Windows":
            found = subprocess.run(["schtasks", "/query", "/tn", NAME], capture_output=True, text=True,
                                   timeout=5).returncode == 0
            return ("ok", "logon task") if found else ("warn", "not managed: it will not start at login")
        if system == "Darwin":
            return ("ok", "launch agent") if paths()["Darwin"].is_file() else \
                ("warn", "not managed: it will not start at login")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "warn", "could not query the service manager (%s)" % type(exc).__name__
    return "skip", system
