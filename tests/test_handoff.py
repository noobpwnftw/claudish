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

    def test_on_windows_a_program_path_with_a_space_is_drafted_in_its_short_form(self):
        with patch.object(handoff.shutil, "which", return_value=None), \
             patch.object(handoff.os, "name", "nt"), \
             patch.object(handoff, "short_path", return_value=r"C:\Users\JOHNSM~1\.local\bin\claude.exe"), \
             patch.object(settings, "claude_code", return_value=r"C:\Users\John Smith\.local\bin\claude.exe"):
            line = handoff.line(["claude", "{prompt}"], "C:\\n.md")
        self.assertTrue(line.startswith(r"C:\Users\JOHNSM~1\.local\bin\claude.exe "), line)  # PowerShell runs it

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

    def test_a_codex_handoff_is_found_whatever_the_notes_path(self):
        """A Windows path is in Codex's session JSON with its backslashes doubled."""
        import json
        import os
        import tempfile
        import time
        for note in (r"C:\Users\me\AppData\Local\Temp\claudish-handoff\h-1234abcd.md", "/run/user/1000/h-1234abcd.md",
                     r"C:\Users\张三\AppData\Local\Temp\h-1234abcd.md"):  # Codex writes non-ASCII as it is
            with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home}):
                day = os.path.join(home, ".codex", "sessions", "2026", "11", "03")
                os.makedirs(day)
                with open(os.path.join(day, "rollout-x.jsonl"), "w", encoding="utf-8") as out:
                    for role, text in (("user", handoff.arguments(["codex", "{prompt}"], note)[1]), ("assistant", "On it")):
                        out.write(json.dumps({"type": "response_item", "timestamp": "t1", "payload": {
                            "type": "message", "role": role, "content": [{"type": "output_text", "text": text}]}}, ensure_ascii=False) + "\n")
                said = handoff.codex_said({"helper": "codex", "note": note, "started": time.time()})
            self.assertEqual(said, (["On it"], "t1"), note)


if __name__ == "__main__":
    unittest.main()


class TerminalLineTests(unittest.TestCase):
    """What goes in at a prompt: one line that runs what was offered."""

    def test_a_multi_line_answer_gives_the_command_not_its_intro(self):
        from claudish.screen import one_line
        cases = {"Run this:\n```bash\nrm -rf build\n```": "rm -rf build",
                 "Undo it with:\n\n    git reset --soft HEAD~1": "git reset --soft HEAD~1",
                 "docker run \\\n -v /a:/b \\\n img": "docker run -v /a:/b img",
                 "```bash ls -la```": "ls -la",
                 "`git status`": "git status",  # the shell would run its output
                 "ls\t-la": "ls -la",  # a tab completes at a prompt
                 "cat <<'EOF' > ~/.bashrc\nexport X=1\nEOF": "",  # half a here-document: nothing
                 "git status": "git status"}
        for answer, offered in cases.items():
            with self.subTest(answer=answer):
                self.assertEqual(one_line(answer), offered)

    def test_a_quoted_command_keeps_its_quotes_at_a_prompt(self):
        from claudish.quirks import tidy
        path = '"C:\\Program Files\\Git\\bin\\bash.exe"'
        self.assertEqual(tidy("open it", path, terminal=True), path)  # cmd runs a quoted path
        self.assertEqual(tidy("open it", '"hello there"'), "hello there")  # elsewhere a wrapping pair goes

    def test_an_argument_a_shell_reads_specially_is_quoted(self):
        with patch.object(handoff, "find_helper", return_value="claude", create=True):
            line = handoff.line(["claude", "{note}"], "/tmp/x(1)/h.md")
        self.assertTrue(line.endswith('"/tmp/x(1)/h.md"'), line)


class AccessibilityBusTests(unittest.TestCase):
    """Without the accessibility bus AT-SPI ends the process: it is asked for first."""

    def test_no_accessibility_bus_reads_nothing(self):
        try:
            from gi.repository import GLib
        except ImportError:
            self.skipTest("no PyGObject")
        from claudish import screen

        def refused(*args):
            raise GLib.Error("The name org.a11y.Bus was not provided by any .service files")
        session = type("Bus", (), {"call_sync": lambda self, *args: refused()})()
        with patch.object(screen, "A11Y_BUS", []), patch.dict("os.environ", {"AT_SPI_BUS_ADDRESS": ""}), \
                patch("gi.repository.Gio.bus_get_sync", return_value=session), \
                patch("gi.require_version", side_effect=AssertionError("AT-SPI loaded")):
            self.assertFalse(screen.accessibility_bus())
            self.assertIsNone(screen.read_atspi("konsole"))
