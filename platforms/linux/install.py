#!/usr/bin/python3
"""Register the Claudish IBus engine. Does not enable it or replace the user's input methods.

IBus (1.5.29 tested) reads components only from IBUS_COMPONENT_PATH, which
defaults to the system directory. A per-user install therefore also writes an
environment.d file that adds the user directory; it takes effect at next login.
"""
import argparse
import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
SYSTEM_COMPONENTS = Path("/usr/share/ibus/component")
USER_COMPONENTS = Path.home() / ".local/share/ibus/component"
ENVIRONMENT = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "environment.d/90-claudish-ibus.conf"

# layout "default" keeps the user's keyboard layout (AltGr, dead keys); the engine works with any layout.
COMPONENT = '''<?xml version="1.0" encoding="utf-8"?>
<component>
  <name>org.freedesktop.IBus.Claudish</name>
  <description>Claudish language model IME</description>
  <exec>/usr/bin/python3 &quot;%s&quot; --ibus</exec>
  <version>0.1.0</version>
  <license>MIT</license>
  <author>Claudish contributors</author>
  <engines><engine>
    <name>claudish</name>
    <longname>cd_AI — Claudish</longname>
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
    print("Log out and back in, then add English → cd_AI — Claudish in Input Sources.")
    print("The source folder must stay in place. Remove with --uninstall%s." % (" --system" if args.system else ""))


if __name__ == "__main__":
    main()
