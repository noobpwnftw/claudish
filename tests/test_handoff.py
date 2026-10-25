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

    def test_on_windows_the_draft_names_the_program_in_full(self):
        with patch.object(handoff.shutil, "which", return_value=None), \
             patch.object(handoff.os, "name", "nt"), \
             patch.object(settings, "claude_code", return_value=r"C:\\Users\\mei\\.local\\bin\\claude.exe"):
            line = handoff.line(["claude", "{prompt}"], "C:\\n.md")
            self.assertTrue(line.startswith(r"C:\\Users\\mei\\.local\\bin\\claude.exe "), line)

    def test_a_program_found_nowhere_is_not_offered(self):
        with patch.object(handoff.shutil, "which", return_value=None), \
             patch.object(settings, "claude_code", return_value=None):
            self.assertEqual(handoff.helpers(["claude", "{prompt}"]), {})


class ProgressTests(unittest.TestCase):
    def test_a_terminal_handoff_is_found_in_whatever_folder_it_ran(self):
        """On the Mac VM, "is it done?" said nothing could be read: a command run at a prompt has no
        known folder, and the transcript was looked for under an empty one."""
        import json
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home}):
            folder = os.path.join(home, ".claude", "projects", "-Users-me-invoices")
            os.makedirs(folder)
            with open(os.path.join(folder, "s1.jsonl"), "w", encoding="utf-8") as out:
                out.write(json.dumps({"type": "assistant", "timestamp": "2026-10-25T13:36:00Z", "message": {
                    "content": [{"type": "text", "text": "Fixed: round(..., 2). The test passes."}]}}) + "\n")
            said, last = handoff.claude_said({"helper": "claude", "session": "s1", "cwd": ""})
        self.assertEqual((said, last), (["Fixed: round(..., 2). The test passes."], "2026-10-25T13:36:00Z"))


if __name__ == "__main__":
    unittest.main()
