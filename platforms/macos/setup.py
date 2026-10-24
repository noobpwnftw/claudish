"""Run from this directory with the macOS build environment."""
import plistlib
import sys
from pathlib import Path
from setuptools import setup

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1]))
with (here / "Info.plist").open("rb") as source:
    info = plistlib.load(source)

setup(
    name="Claudish",
    version="0.1.0",
    app=[{"script": "main.py", "dest_base": "Claudish"}],
    options={"py2app": {"plist": info,
                        "includes": ["controller", "panel", "sources", "InputMethodKit", "AppKit", "Foundation"],
                        # the Claude backend, for the service the bundle also runs (G61)
                        # certifi as files, not zipped: the HTTP client opens its cacert.pem by path
                        "packages": ["claudish", "anthropic", "certifi"],
                        "argv_emulation": False,
                        # the input source's name and menu-bar icon (cd.tiff: build.py makes it)
                        "resources": ["cd.tiff", "en.lproj"]}},
)
