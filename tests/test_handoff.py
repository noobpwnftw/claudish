import unittest
from unittest.mock import patch

from claudish import handoff, settings


class HelperDiscoveryTests(unittest.TestCase):
    """A login service may not have the shell's PATH: a helper is found where Claude Code's installer
    puts it, as the Claude Code backend is (on the Mac VM, plain "claude" was never offered)."""

    def test_claude_off_the_path_is_offered_and_a_window_gets_its_path(self):
        with patch.object(handoff.shutil, "which", return_value=None), \
             patch.object(handoff, "unsupervised_claude", return_value=False), \
             patch.object(settings, "claude_code", return_value="/Users/me/.local/bin/claude"):
            template = ["claude", "--session-id", "{session}", "{prompt}"]
            self.assertIn("claude", handoff.helpers(template))
            self.assertEqual(handoff.arguments(template, "/tmp/n.md", "s1", resolve=True)[0], "/Users/me/.local/bin/claude")
            self.assertTrue(handoff.line(template, "/tmp/n.md", "s1").startswith("claude --session-id s1 "))

    def test_a_program_found_nowhere_is_not_offered(self):
        with patch.object(handoff.shutil, "which", return_value=None), \
             patch.object(settings, "claude_code", return_value=None):
            self.assertEqual(handoff.helpers(["claude", "{prompt}"]), {})


if __name__ == "__main__":
    unittest.main()
