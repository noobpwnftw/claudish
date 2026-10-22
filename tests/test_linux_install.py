import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INSTALL = Path(__file__).resolve().parents[1] / "platforms/linux/install.py"


@unittest.skipIf(os.name == "nt", "the IBus installer is Linux-only")
class LinuxInstallTests(unittest.TestCase):
    def run_install(self, home, *args, **env):
        environment = {k: v for k, v in os.environ.items() if k not in ("IBUS_COMPONENT_PATH", "XDG_CONFIG_HOME")}
        environment.update(HOME=home, **env)
        return subprocess.run([sys.executable, str(INSTALL), *args], env=environment, capture_output=True, text=True)

    def test_user_install_adds_search_path_and_uninstalls_cleanly(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(self.run_install(home).returncode, 0)
            component = Path(home, ".local/share/ibus/component/claudish.xml")
            setting = Path(home, ".config/environment.d/90-claudish-ibus.conf")
            xml = component.read_text(encoding="utf-8")
            self.assertIn("<layout>default</layout>", xml)  # Keep the user's layout (AltGr, dead keys).
            self.assertIn("platforms/linux/engine.py", xml)
            self.assertEqual(setting.read_text(),
                             "IBUS_COMPONENT_PATH=/usr/share/ibus/component:%s/.local/share/ibus/component\n" % home)
            self.assertEqual(self.run_install(home, "--uninstall").returncode, 0)
            self.assertFalse(component.exists() or setting.exists())

    def test_existing_component_path_is_kept(self):
        with tempfile.TemporaryDirectory() as home:
            self.run_install(home, IBUS_COMPONENT_PATH="/opt/ibus/component:/usr/share/ibus/component")
            setting = Path(home, ".config/environment.d/90-claudish-ibus.conf").read_text()
            self.assertEqual(setting, "IBUS_COMPONENT_PATH=/opt/ibus/component:/usr/share/ibus/component:"
                                      "%s/.local/share/ibus/component\n" % home)


if __name__ == "__main__":
    unittest.main()
