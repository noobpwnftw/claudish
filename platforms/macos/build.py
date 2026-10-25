"""Build a standalone local-development input method on macOS."""
import argparse
import shutil
import subprocess
import sys
import venv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Build the Claudish macOS input source")
    parser.add_argument("--install", action="store_true", help="Copy into ~/Library/Input Methods")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("App bundling requires macOS; run this command on a Mac")
    here = Path(__file__).resolve().parent
    root = here.parents[1]
    target = Path.home() / "Library/Input Methods/Claudish.app"
    if args.install and target.exists():
        parser.error("Claudish.app is already installed; switch input sources and remove the old app first")
    environment = root / ".tools/macos-build-venv"
    if not (environment / "bin/python").exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = str(environment / "bin/python")
    subprocess.run([python, "-m", "pip", "install", "-r", str(here / "requirements-build.txt")], check=True)
    # The menu-bar icon: macOS loads TIFF for input sources (the PNGs tried were not shown); one TIFF
    # with the 1x and 2x renders (scripts/make_icon.py), so it is sharp on Retina screens.
    for name in ("cd", "ai"):  # continue's and compose's
        subprocess.run(["tiffutil", "-cathidpicheck", str(here / (name + ".png")), str(here / (name + "@2x.png")),
                        "-out", str(here / (name + ".tiff"))], check=True, capture_output=True)
    subprocess.run([python, "setup.py", "py2app", "--dist-dir", str(root / "dist/macos"),
                    "--bdist-base", str(root / "build/macos")], cwd=here, check=True)
    bundle = root / "dist/macos/Claudish.app"
    # Development signing only; release distribution needs a Developer ID and notarization.
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True)
    print("Built:", bundle)
    if args.install:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundle, target, symlinks=True)
        print("Installed:", target)
        print("Log out and back in, then add cd_AI (under English) in System Settings → Keyboard → Text Input → Edit.")
        print("The service: `claudish setup`, or the bundle's own `Claudish service install`.")


if __name__ == "__main__":
    main()
