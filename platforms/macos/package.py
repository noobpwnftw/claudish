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
# Installed for the person installing it: run as root (sudo installer), $HOME and the login
# service would be root's.
[ "$(id -u)" = 0 ] && { echo "cd_AI installs for you, not as root: install it without sudo" >&2; exit 1; }
app="$2/Claudish.app"
[ -d "$app" ] || app="$HOME/Library/Input Methods/Claudish.app"
cd_ai="$app/Contents/MacOS/Claudish"
mkdir -p "$HOME/Library/Logs"
exec >> "$HOME/Library/Logs/cd_AI-install.log" 2>&1
date
# A reinstall: stop the old build, as Squirrel's installer does, and start the service again below.
# As with Squirrel, logging out and back in finishes an install or an update (docs/install.md).
launchctl bootout "gui/$(id -u)/com.claudish.service" 2> /dev/null
killall Claudish 2> /dev/null
[ -f "$HOME/.config/claudish/config.json" ] || first=1
"$cd_ai" init > /dev/null 2>&1 || true
"$cd_ai" service install
"$cd_ai" register  # added and enabled, not selected
# The first install ends in cd_AI's settings in the browser (the key, the tone); an update opens nothing.
[ -n "$first" ] && "$cd_ai" settings --first
exit 0
"""

CONCLUSION = """<!doctype html><meta charset="utf-8">
<body style="font: 13px -apple-system, sans-serif">
<p><b>Log out and back in to finish.</b> macOS loads a new input method at login.</p>
<p>Then pick <b>cd_AI</b> in the input menu (the menu bar, or Control–Space), type a few words in
any app, and press <b>Tab</b>. Settings… in that menu changes the key and the tone.</p>
</body>
"""

COMPONENTS = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><array><dict>
    <key>RootRelativeBundlePath</key><string>Claudish.app</string>
    <key>BundleIsRelocatable</key><false/>
    <key>BundleIsVersionChecked</key><false/>
    <key>BundleHasStrictIdentifier</key><true/>
    <key>BundleOverwriteAction</key><string>upgrade</string>
</dict></array></plist>
"""

DISTRIBUTION = """<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>cd_AI</title>
    <domains enable_anywhere="false" enable_currentUserHome="true" enable_localSystem="false"/>
    <options customize="never" require-scripts="false" hostArchitectures="{architectures}"/>
    <choices-outline><line choice="cd_AI"/></choices-outline>
    <choice id="cd_AI" title="cd_AI"><pkg-ref id="{identifier}"/></choice>
    <pkg-ref id="{identifier}" version="{version}" onConclusion="none">component.pkg</pkg-ref>
    <conclusion file="conclusion.html" mime-type="text/html"/>
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
    sources = [p for d in ("claudish", "platforms/macos") for p in (ROOT / d).rglob("*")
               if p.is_file() and "__pycache__" not in p.parts]
    if max(p.stat().st_mtime for p in sources) > (bundle / "Contents/Info.plist").stat().st_mtime:
        parser.error("%s is older than the sources: build it again (platforms/macos/build.py)" % bundle)
    import plistlib
    version = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())["CFBundleShortVersionString"]
    # The architectures every binary in the bundle runs on, so Installer refuses a Mac it cannot run
    # on: the launcher is universal, but a module pip installed (pydantic_core, for the Claude
    # backend) can be built for this Mac's architecture only.
    built = None
    for binary in [bundle / "Contents/MacOS/Claudish"] + sorted(bundle.rglob("*.so")) + sorted(bundle.rglob("*.dylib")):
        archs = subprocess.run(["lipo", "-archs", str(binary)], capture_output=True, text=True).stdout.split()
        if archs:
            built = set(archs) if built is None else built & set(archs)
    built = sorted(built or [])
    if not built:  # no architecture common to every binary: the package would install nowhere
        parser.error("lipo found no architecture common to the bundle's binaries; rebuild it on this Mac")
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        payload, scripts = work / "payload", work / "scripts"
        payload.mkdir()
        scripts.mkdir()
        subprocess.run(["ditto", str(bundle), str(payload / "Claudish.app")], check=True)
        (scripts / "postinstall").write_text(POSTINSTALL)
        (scripts / "postinstall").chmod(0o755)
        # Not relocatable: Installer would otherwise update any other Claudish.app it finds (a
        # development build) instead of installing this one where it belongs.
        (work / "components.plist").write_text(COMPONENTS)
        subprocess.run(["pkgbuild", "--root", str(payload), "--install-location", "/Library/Input Methods",
                        "--component-plist", str(work / "components.plist"),
                        "--scripts", str(scripts), "--identifier", IDENTIFIER, "--version", version,
                        str(work / "component.pkg")], check=True)
        resources = work / "resources"
        resources.mkdir()
        (resources / "conclusion.html").write_text(CONCLUSION)
        (work / "distribution.xml").write_text(DISTRIBUTION.format(
            identifier=IDENTIFIER, version=version,
            architectures=",".join(built)))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["productbuild", "--distribution", str(work / "distribution.xml"),
                        "--package-path", str(work), "--resources", str(resources), str(args.out)], check=True)
    print("Built:", args.out)


if __name__ == "__main__":
    main()
