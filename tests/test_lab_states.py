"""The design lab draws what the input method draws: claudish/web/lab-states.js is generated from
claudish/composition.py (scripts/lab_states.py) and must be current."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LabStatesTests(unittest.TestCase):
    def test_the_labs_panels_are_composition_s(self):
        done = subprocess.run([sys.executable, str(ROOT / "scripts/lab_states.py"), "--check"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_every_lab_card_has_its_panel(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import lab_states
        states = lab_states.load()
        cards = (ROOT / "claudish/web/design.js").read_text(encoding="utf-8")
        for name in states:
            self.assertIn('{id: "%s"' % name, cards)


if __name__ == "__main__":
    unittest.main()
