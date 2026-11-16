import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish import keys


class LoginProfileTests(unittest.TestCase):
    """An `ant auth login` profile counts where the Anthropic SDK finds one, not an empty folder."""

    def found(self, home, platform="linux", **env):
        clean = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_CONFIG_DIR", "ANTHROPIC_PROFILE", "APPDATA")}
        with patch.dict(os.environ, dict(clean, **env), clear=True), patch.object(Path, "home", return_value=home), \
                patch("sys.platform", platform):
            return keys.anthropic_profile()

    def test_the_active_profile_file_counts_not_the_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            folder = home / ".config/anthropic"
            folder.mkdir(parents=True)
            self.assertFalse(self.found(home))  # an empty or stale folder: no login
            (folder / "configs").mkdir()
            (folder / "configs/work.json").write_text("{}")
            self.assertFalse(self.found(home))  # "default" is the active one
            (folder / "active_config").write_text("work\n")
            self.assertTrue(self.found(home))
            self.assertFalse(self.found(home, ANTHROPIC_PROFILE="other"))
            self.assertFalse(self.found(home, ANTHROPIC_CONFIG_DIR=str(home / "elsewhere")))
            self.assertTrue(self.found(home, ANTHROPIC_CONFIG_DIR=str(folder)))

    def test_windows_looks_in_appdata(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "Roaming/Anthropic/configs").mkdir(parents=True)
            (home / "Roaming/Anthropic/configs/default.json").write_text("{}")
            self.assertTrue(self.found(home, "win32", APPDATA=str(home / "Roaming")))
            self.assertFalse(self.found(home))


if __name__ == "__main__":
    unittest.main()
