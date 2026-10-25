"""`claudish service install|uninstall|status`: start the service at login, without a terminal.

Linux: a systemd user unit. Windows: a logon task (pythonw, no console). macOS: a launchd agent.
By default `claudish serve ARGS` (the config's profile); with --local, the optional local stack
(scripts/start.py: a local model and the service).
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


def task_name():
    """Windows' logon task, one per account: a machine-wide name was taken by whoever installed first,
    and another account's install could not replace it, so its service never started at login."""
    import re
    return "%s-%s" % (NAME, re.sub(r"[^A-Za-z0-9_.-]", "_", os.environ.get("USERNAME", "") or "user"))
LABEL = "com.claudish.service"


def command(local, extra):
    """The argv the service manager runs: inside the macOS bundle, the bundle itself (G61)."""
    if getattr(sys, "frozen", False) and os.environ.get("EXECUTABLEPATH"):
        return [os.environ["EXECUTABLEPATH"], "serve"] + list(extra)  # py2app's launcher sets it
    if local:
        return [sys.executable, str(ROOT / "scripts" / "start.py")] + list(extra)
    if not (ROOT / "scripts" / "serve.py").is_file():  # installed as a package (the Windows installer)
        return [sys.executable, "-m", "claudish", "serve"] + list(extra)
    return [sys.executable, str(ROOT / "scripts" / "serve.py")] + list(extra)


def typed():
    """How a person runs claudish here: `claudish` when that is on PATH and is this install, the
    bundle's own command on macOS, else this Python with -m claudish."""
    import shutil
    if getattr(sys, "frozen", False) and os.environ.get("EXECUTABLEPATH"):
        return shlex_quote(os.environ["EXECUTABLEPATH"])
    found = shutil.which("claudish")
    here = os.path.join(os.path.dirname(sys.executable), "claudish")
    windows = os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "bin", "claudish.cmd")  # the installer's
    same = lambda path: os.path.normcase(os.path.realpath(path))  # Windows: which() may say claudish.CMD
    if found and same(found) in (same(here), same(here + ".exe"), same(windows)):
        return "claudish"
    return "%s -m claudish" % shlex_quote(sys.executable)


def shlex_quote(path):
    return '"%s"' % path if " " in path else path


def as_typed(text):
    """A hint's `claudish ...` commands, as they run here."""
    command = typed()
    return text if command == "claudish" else text.replace("`claudish ", "`%s " % command)


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
    """The logon task's XML: pythonw instead of python, so no console window appears at login. This
    account's logon only (an any-user trigger needs an administrator), on battery too, no time limit
    (schtasks /create stops a task after 72 hours), normal priority (its default is below normal)."""
    program = Path(argv[0])
    pythonw = program.with_name("pythonw.exe")
    user = escape("%s\\%s" % (os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")))
    return """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>%s</UserId></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>%s</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>5</Priority>
  </Settings>
  <Actions Context="Author"><Exec><Command>%s</Command><Arguments>%s</Arguments></Exec></Actions>
</Task>
""" % (user, user, escape(str(pythonw if pythonw.is_file() else program)), escape(subprocess.list2cmdline(argv[1:])))


def launchd_plist(argv):
    """Interactive, as an app: the input method waits on this service from the first key, and a
    login agent's default scheduling left it starting for 40 s while the login settled."""
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
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ProcessType</key><string>Interactive</string>
</dict>
</plist>
""" % (LABEL, arguments, escape(str(ROOT)))


def paths():
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return {"Linux": config / ("systemd/user/%s.service" % NAME),
            "Windows": config / NAME / "logon-task.xml",
            "Darwin": home / ("Library/LaunchAgents/%s.plist" % LABEL)}


def plan(action, local=False, extra=()):
    """[(description, kind, payload)]: "write" (path, text), "run" (argv), "stop" (argv; may find
    nothing to stop), or "remove" (path)."""
    system, argv = platform.system(), command(local, extra)
    if system == "Linux":
        unit = paths()["Linux"]
        if action == "install":
            return [("write the systemd user unit", "write", (unit, systemd_unit(argv))),
                    ("reload systemd", "run", ["systemctl", "--user", "daemon-reload"]),
                    ("enable it", "run", ["systemctl", "--user", "enable", NAME]),
                    ("start it, or restart it with these settings", "run", ["systemctl", "--user", "restart", NAME])]
        if action == "uninstall":
            return [("stop and disable it", "run", ["systemctl", "--user", "disable", "--now", NAME]),
                    ("remove the unit", "remove", unit),
                    ("reload systemd", "run", ["systemctl", "--user", "daemon-reload"])]
        return [("status", "run", ["systemctl", "--user", "is-active", NAME])]
    if system == "Windows":
        if action == "install":
            task = paths()["Windows"]
            return [("drop the shared logon task an older cd_AI made (if this account's)", "stop",
                     ["schtasks", "/delete", "/tn", NAME, "/f"]),
                    ("write the logon task", "write", (task, windows_task(argv), "utf-16")),
                    ("create the logon task", "run", ["schtasks", "/create", "/tn", task_name(), "/xml", str(task), "/f"]),
                    ("start it now", "run", ["schtasks", "/run", "/tn", task_name()])]
        if action == "uninstall":
            return [("stop it", "run", ["schtasks", "/end", "/tn", task_name()]),
                    ("delete the logon task", "run", ["schtasks", "/delete", "/tn", task_name(), "/f"])]
        return [("status", "run", ["schtasks", "/query", "/tn", task_name()])]
    if system == "Darwin":
        agent, domain = paths()["Darwin"], "gui/%d" % os.getuid()
        if action == "install":
            return [("stop a running one", "stop", ["launchctl", "bootout", "%s/%s" % (domain, LABEL)]),
                    ("write the launch agent", "write", (agent, launchd_plist(argv))),
                    ("load it", "run", ["launchctl", "bootstrap", domain, str(agent)])]
        if action == "uninstall":
            return [("unload it", "run", ["launchctl", "bootout", "%s/%s" % (domain, LABEL)]),
                    ("remove the launch agent", "remove", agent)]
        return [("status", "run", ["launchctl", "print", "%s/%s" % (domain, LABEL)])]
    raise SystemExit("no service manager support for %s" % system)


def run(action, local=False, extra=(), dry_run=False):
    steps = plan(action, local, extra)
    for description, kind, payload in steps:
        if dry_run:
            shown = payload[0] if kind == "write" else payload if kind == "remove" else subprocess.list2cmdline(payload)
            print("would %s: %s" % (description, shown))
            if kind == "write":
                print(payload[1])
            continue
        if kind == "write":
            path, text = payload[:2]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding=payload[2] if len(payload) > 2 else "utf-8")
        elif kind == "remove":
            if payload.exists():
                payload.unlink()
        else:
            result = subprocess.run(payload, capture_output=True, text=True)
            if action == "status":
                print((result.stdout or result.stderr).strip() or ("active" if result.returncode == 0 else "inactive"))
                return result.returncode
            # Stopping something that is not running is fine.
            if result.returncode != 0 and action != "uninstall" and kind != "stop":
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
            found = subprocess.run(["schtasks", "/query", "/tn", task_name()], capture_output=True, text=True,
                                   timeout=5).returncode == 0
            return ("ok", "logon task") if found else ("warn", "not managed: it will not start at login")
        if system == "Darwin":
            return ("ok", "launch agent") if paths()["Darwin"].is_file() else \
                ("warn", "not managed: it will not start at login")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "warn", "could not query the service manager (%s)" % type(exc).__name__
    return "skip", system
