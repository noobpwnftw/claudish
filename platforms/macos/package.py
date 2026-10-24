"""Build cd_AI.pkg from the bundle build.py made (G61): one download, no Developer ID.

python platforms/macos/package.py [--out dist/macos/cd_AI.pkg]

The package installs for the current user only (~/Library/Input Methods), so it asks for no
administrator password, and its postinstall stops a cd_AI already running (a reinstall) and does
the first run (ending, on a first install, in the settings window) with the bundle's own command line:
a starter config (an existing one is kept), the service at every login, and the input source added
and enabled (macOS asks once: "Allow … to enable cd_AI?"). Ad-hoc signed like the bundle: a
browser download is blocked once, and System Settings > Privacy & Security > Open Anyway lets it
through (docs/research/2026-10-24-install-poll.md).
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
IDENTIFIER = "org.claudish.inputmethod.Claudish.pkg"

POSTINSTALL = """#!/bin/sh
# cd_AI's first run: a starter config, the service at every login, the input source added and
# enabled. $2 is where the package put the bundle (~/Library/Input Methods for this user).
app="$2/Claudish.app"
[ -d "$app" ] || app="$HOME/Library/Input Methods/Claudish.app"
cd_ai="$app/Contents/MacOS/Claudish"
# A reinstall: stop the old build, as Squirrel's installer does; macOS starts the new input method
# on the next key, and the service is started again below.
launchctl bootout "gui/$(id -u)/com.claudish.service" 2> /dev/null
killall Claudish 2> /dev/null
[ -f "$HOME/.config/claudish/config.json" ] || first=1
"$cd_ai" init > /dev/null 2>&1 || true
"$cd_ai" service install
"$cd_ai" register
# The first install ends in the settings window (the key, the voice); an update opens nothing.
[ -n "$first" ] && open -n "$app" --args settings
exit 0
"""

DISTRIBUTION = """<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>cd_AI</title>
    <domains enable_anywhere="false" enable_currentUserHome="true" enable_localSystem="false"/>
    <options customize="never" require-scripts="false" hostArchitectures="arm64,x86_64"/>
    <choices-outline><line choice="cd_AI"/></choices-outline>
    <choice id="cd_AI" title="cd_AI"><pkg-ref id="{identifier}"/></choice>
    <pkg-ref id="{identifier}" version="{version}" onConclusion="none">component.pkg</pkg-ref>
</installer-gui-script>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "dist/macos/cd_AI.pkg")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Packages are built on macOS")
    bundle = ROOT / "dist/macos/Claudish.app"
    if not bundle.is_dir():
        parser.error("build the bundle first: python platforms/macos/build.py")
    version = "0.1.0"
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        payload, scripts = work / "payload", work / "scripts"
        payload.mkdir()
        scripts.mkdir()
        subprocess.run(["ditto", str(bundle), str(payload / "Claudish.app")], check=True)
        (scripts / "postinstall").write_text(POSTINSTALL)
        (scripts / "postinstall").chmod(0o755)
        subprocess.run(["pkgbuild", "--root", str(payload), "--install-location", "/Library/Input Methods",
                        "--scripts", str(scripts), "--identifier", IDENTIFIER, "--version", version,
                        str(work / "component.pkg")], check=True)
        (work / "distribution.xml").write_text(DISTRIBUTION.format(identifier=IDENTIFIER, version=version))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["productbuild", "--distribution", str(work / "distribution.xml"),
                        "--package-path", str(work), str(args.out)], check=True)
    print("Built:", args.out)


if __name__ == "__main__":
    main()
