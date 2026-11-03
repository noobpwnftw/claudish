"""The Compose key's table (claudish/x11_compose.py), read as GTK reads the X11 compose files."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish import x11_compose


class ComposeTableTests(unittest.TestCase):
    def test_sequences_escapes_and_your_own_file_over_the_systems(self):
        with tempfile.TemporaryDirectory() as folder:
            system, own = Path(folder, "Compose"), Path(folder, ".XCompose")
            system.write_text("\n".join([
                '<Multi_key> <o> <c> : "\u00a9" copyright',
                '<Multi_key> <minus> <minus> <minus> : "\u2014" emdash',
                '<dead_acute> <e> : "\u00e9"',  # not a Compose-key sequence
                r'<Multi_key> <quotedbl> <backslash> : "\"\\"']) + "\n", encoding="utf-8")
            own.write_text('include "%L"\n<Multi_key> <o> <c> : "(c)"\n', encoding="utf-8")
            with patch.object(x11_compose, "SYSTEM", (str(system),)), \
                    patch.dict(os.environ, {"XCOMPOSEFILE": str(own)}):
                compose = x11_compose.Compose()
        self.assertEqual(compose.step(["o", "c"]), ("text", "(c)"))
        self.assertEqual(compose.step(["minus", "minus"]), ("wait", None))
        self.assertEqual(compose.step(["minus", "minus", "minus"]), ("text", "\u2014"))
        self.assertEqual(compose.step(["quotedbl", "backslash"]), ("text", '"\\'))
        self.assertEqual(compose.step(["e"]), ("none", None))


if __name__ == "__main__":
    unittest.main()
