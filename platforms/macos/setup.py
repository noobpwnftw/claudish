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
    version="0.1.1",
    app=[{"script": "main.py", "dest_base": "Claudish"}],
    options={"py2app": {"plist": info,
                        # _cffi_backend: cryptography (under MCP) loads it from compiled code, where
                        # py2app's scan does not see it; without it importing mcp fails in the bundle.
                        "includes": ["controller", "panel", "sources", "InputMethodKit", "AppKit", "Foundation",
                                     "_cffi_backend"],
                        # Cocoa supplies the UI. Tk's recipe opens a GUI during bundling and can
                        # abort when building over SSH from a logged-out account.
                        "excludes": ["tkinter"],
                        # the Claude backend and MCP (tools and context), for the service the bundle also runs
                        # certifi as files, not zipped: the HTTP client opens its cacert.pem by path
                        # anyio: loads its asyncio backend by name at run time, past the scan
                        "packages": ["claudish", "anthropic", "mcp", "anyio", "certifi"],
                        "argv_emulation": False,
                        # the input source's name and menu-bar icon (cd.tiff: build.py makes it)
                        "resources": ["cd.tiff", "en.lproj"]}},
)
