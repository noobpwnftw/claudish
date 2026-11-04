"""The release version is written in each platform's package files: they all say the same."""
import json
import plistlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class VersionTest(unittest.TestCase):
    def test_every_copy_matches_pyproject(self):
        version = re.search(r'^version = "([^"]+)"', read("pyproject.toml"), re.M).group(1)
        with (ROOT / "platforms/macos/Info.plist").open("rb") as source:
            plist = plistlib.load(source)["CFBundleShortVersionString"]
        copies = {
            "platforms/linux/install.py": re.search(r"<version>([^<]+)</version>", read("platforms/linux/install.py")).group(1),
            "platforms/windows/claudish/ime.json": json.loads(read("platforms/windows/claudish/ime.json"))["version"],
            "platforms/macos/Info.plist": plist,
            "scripts/install.sh": re.search(r"CLAUDISH_REF:-v([^}]+)}", read("scripts/install.sh")).group(1),
        }
        self.assertEqual({path: version for path in copies}, copies)


if __name__ == "__main__":
    unittest.main()
