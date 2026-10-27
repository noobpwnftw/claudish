#!/usr/bin/python3
"""Register the Claudish IBus engine. Does not enable it or replace the user's input methods.

IBus (1.5.29 tested) reads components only from IBUS_COMPONENT_PATH, which
defaults to the system directory. A per-user install therefore also writes an
environment.d file that adds the user directory; it takes effect at next login.

On GNOME it also installs and enables cd_AI's GNOME Shell extension (gnome-extension/), which
draws cd_AI's panel and suggestion at the caret; it draws nothing unless cd_AI is typing.
"""
import argparse
import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
SYSTEM_COMPONENTS = Path("/usr/share/ibus/component")
USER_COMPONENTS = Path.home() / ".local/share/ibus/component"
ENVIRONMENT = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "environment.d/90-claudish-ibus.conf"
EXTENSION = "cd-ai@claudish.io"
EXTENSIONS = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "gnome-shell/extensions"

# layout "default" keeps the user's keyboard layout (AltGr, dead keys); the engine works with any layout.
COMPONENT = '''<?xml version="1.0" encoding="utf-8"?>
<component>
  <name>org.freedesktop.IBus.Claudish</name>
  <description>Claudish language model IME</description>
  <exec>/usr/bin/python3 &quot;%s&quot; --ibus</exec>
  <version>0.3.1</version>
  <license>MIT</license>
  <author>Claudish contributors</author>
  <engines><engine>
    <name>claudish</name>
    <longname>Claudish</longname>
    <description>English goes in, em dashes come out</description>
    <language>en</language>
    <license>MIT</license>
    <author>Claudish contributors</author>
    <layout>default</layout>
    <symbol>cd</symbol>
  </engine></engines>
</component>
'''


def component_path_setting():
    existing = [part for part in os.environ.get("IBUS_COMPONENT_PATH", "").split(":") if part]
    parts = existing or [str(SYSTEM_COMPONENTS)]
    if str(USER_COMPONENTS) not in parts:
        parts.append(str(USER_COMPONENTS))
    return "IBUS_COMPONENT_PATH=%s\n" % ":".join(parts)


def enabled_extensions():
    found = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                           capture_output=True, text=True)
    if found.returncode != 0:
        return None
    value = found.stdout.strip()
    return list(ast.literal_eval(value[value.index("["):])) if "[" in value else []


def set_extension(enabled):
    """Link (or unlink) the GNOME Shell extension for this user and list it as enabled; it loads at
    the next login (GNOME Shell on Wayland cannot reload)."""
    link = EXTENSIONS / EXTENSION
    if enabled:
        EXTENSIONS.mkdir(parents=True, exist_ok=True)
        target = ROOT / "platforms/linux/gnome-extension" / EXTENSION
        if link.is_symlink() and link.resolve() != target.resolve():
            link.unlink()  # an older checkout's (moved or gone): this one's instead
        if not link.is_symlink() and not link.exists():
            link.symlink_to(target)
    elif link.is_symlink():
        link.unlink()
    current = enabled_extensions()
    if current is None:
        return False
    wanted = sorted(set(current) | {EXTENSION}) if enabled else [e for e in current if e != EXTENSION]
    if wanted != current:
        subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(wanted)], check=False)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--system", action="store_true", help="Install for all users (run with sudo)")
    parser.add_argument("--uninstall", action="store_true", help="Remove what this script installed")
    args = parser.parse_args()
    directory = SYSTEM_COMPONENTS if args.system else USER_COMPONENTS
    component = directory / "claudish.xml"
    if args.uninstall:
        for path in [component] + ([] if args.system else [ENVIRONMENT]):
            if path.exists():
                path.unlink()
                print("Removed", path)
        if not args.system and shutil.which("gnome-shell"):
            set_extension(False)
            print("Removed the GNOME Shell extension", EXTENSION)
        print("Log out and back in (or run `ibus restart`) to finish.")
        return
    try:
        directory.mkdir(parents=True, exist_ok=True)
        component.write_text(COMPONENT % escape(str(ROOT / "platforms/linux/engine.py")), encoding="utf-8")
    except PermissionError:
        sys.exit("Permission denied writing %s; use sudo with --system." % component)
    print("Registered", component)
    if not args.system:
        ENVIRONMENT.parent.mkdir(parents=True, exist_ok=True)
        ENVIRONMENT.write_text(component_path_setting(), encoding="utf-8")
        print("Added the user component directory to IBus's search path in", ENVIRONMENT)
        print("If your session does not read environment.d, use `sudo %s --system` instead." % sys.argv[0])
        if shutil.which("gnome-shell"):
            if set_extension(True):
                print("Installed and enabled the GNOME Shell extension", EXTENSION, "(it draws cd_AI's panel)")
            else:
                print("Linked the GNOME Shell extension %s; enable it in Extensions." % EXTENSION)
    print("Log out and back in, then add English → Claudish in Input Sources.")
    print("The source folder must stay in place. Remove with --uninstall%s." % (" --system" if args.system else ""))


if __name__ == "__main__":
    main()
