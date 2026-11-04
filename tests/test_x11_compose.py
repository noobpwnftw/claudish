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
                '<dead_belowdot> <e> : "\u1eb9"',  # a dead key's sequence (Vietnamese's dot below)
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
        self.assertEqual(compose.step(["dead_belowdot"]), ("wait", None))
        self.assertEqual(compose.step(["dead_belowdot", "e"]), ("text", "\u1eb9"))


if __name__ == "__main__":
    unittest.main()


class ComposeFileFormTests(unittest.TestCase):
    def test_includes_escapes_keysym_results_and_a_longer_sequence_of_your_own(self):
        with tempfile.TemporaryDirectory() as folder:
            system, own, extra = Path(folder, "Compose"), Path(folder, ".XCompose"), Path(folder, "extra")
            system.write_text('<Multi_key> <o> <c> : "\\u00a9"\n<Multi_key> <period> <period> : ellipsis\n',
                              encoding="utf-8")
            extra.write_text('<Multi_key> <z> <z> : "zed"\n', encoding="utf-8")
            own.write_text('include "%L"\ninclude "' + str(extra) + '"\n'
                           r'<Multi_key> <m> <d> : "\342\200\224"' + "\n"
                           '<Multi_key> <o> <c> <x> : "longer"\n'
                           '<Multi_key> <U01a1> : "horn"\n', encoding="utf-8")
            with patch.object(x11_compose, "SYSTEM", (str(system),)), \
                    patch.dict(os.environ, {"XCOMPOSEFILE": str(own)}):
                compose = x11_compose.Compose(key=lambda name: {"ellipsis": "\u2026", "period": "."}.get(name, name))
        self.assertEqual(compose.step(["z", "z"]), ("text", "zed"))  # an included file
        self.assertEqual(compose.step(["m", "d"]), ("text", "\u2014"))  # UTF-8 bytes in octal
        self.assertEqual(compose.step([".", "."]), ("text", "\u2026"))  # a keysym's own character
        self.assertEqual(compose.step(["o", "c"]), ("wait", None))  # replaced by your longer one
        self.assertEqual(compose.step(["o", "c", "x"]), ("text", "longer"))
        self.assertEqual(compose.step(["\u01a1"]), ("text", "horn"))  # <U01a1>, any case: the character
