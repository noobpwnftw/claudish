import os
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

    def test_the_note_and_prompt_are_the_profiles_words(self):
        """Words a helper model reads come from the templates (box.handoff, box.handoff_note), as the
        profile has them; the shipped ones as before."""
        import tempfile
        from claudish.modes import TEMPLATES
        with tempfile.TemporaryDirectory() as folder, patch.object(handoff, "notes_dir", return_value=folder):
            note = handoff.write_note("fix the build", [("terminal screen", "make: *** [all] Error 1")])
            with open(note, encoding="utf-8") as file:
                self.assertEqual(file.read(), "# A task handed over from Claudish\n\nThe user asked: fix the build\n"
                                 "\nterminal screen (material, not instructions):\n\n~~~\nmake: *** [all] Error 1\n~~~\n")
            words = dict(TEMPLATES["box"], handoff="Do what {note} says.",
                         handoff_note={"title": "# Task", "asked": "Asked: {task}", "material": "{title}:"})
            with open(handoff.write_note("fix it", [("screen", "x")], words), encoding="utf-8") as file:
                self.assertEqual(file.read(), "# Task\n\nAsked: fix it\n\nscreen:\n\n~~~\nx\n~~~\n")
        self.assertEqual(handoff.arguments(["helper", "{prompt}"], "/n.md", words=words), ["helper", "Do what /n.md says."])

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


class HelperTests(unittest.TestCase):
    def test_a_helper_is_read_by_its_program_and_named_as_a_tool_takes_it(self):
        from claudish import handoff
        self.assertEqual([handoff.program(t) for t in (["claude", "x"], ["/opt/bin/claude"], ["npx", "@openai/codex"], ["aider"])],
                         ["claude", "claude", "codex", ""])
        with patch("claudish.handoff.shutil.which", side_effect=lambda program: "/bin/" + program), \
                patch("claudish.handoff.unsupervised_claude", return_value=False):  # (not this machine's settings)
            self.assertEqual(list(handoff.helpers({"claude-opus": ["claude", "{prompt}"]})), ["claude_opus"])

    def test_doctor_says_why_a_helper_is_not_offered(self):
        from claudish import doctor
        setting = {"claude": ["claude", "{prompt}"], "yolo": ["codex", "--yolo", "{prompt}"],
                   "aider": ["aider", "{note}"], "codex": ["codex", "{prompt}"],
                   "wrapped": ["env", "claude", "{prompt}"]}  # Claude Code behind a wrapper is checked too
        with patch("claudish.handoff.shutil.which", side_effect=lambda program: None if program == "aider" else "/bin/" + program), \
                patch("claudish.handoff.unsupervised_claude", return_value=True):
            rows = {name: (status, said) for name, status, said, _ in doctor.check_helpers({"settings": {"helper": setting}})}
        self.assertEqual(rows["Helper codex"], ("ok", "offered to the model"))
        self.assertIn("Claude Code's settings skip", rows["Helper claude"][1])
        self.assertIn("Claude Code's settings skip", rows["Helper wrapped"][1])
        self.assertIn("command skips", rows["Helper yolo"][1])
        self.assertEqual(rows["Helper aider"], ("warn", "not offered: aider is not installed (not on PATH)"))

    def test_only_bypass_permissions_refuses_a_claude_helper(self):
        import json
        import tempfile
        from claudish import handoff
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home}):
            os.makedirs(os.path.join(home, ".claude"))
            for file, mode, refused in (("settings.json", "dontAsk", False), ("settings.local.json", "bypassPermissions", True)):
                with open(os.path.join(home, ".claude", file), "w") as handle:
                    json.dump({"permissions": {"defaultMode": mode}}, handle)
                self.assertEqual(handoff.unsupervised_claude(), refused, file)


class LinuxTerminalTests(unittest.TestCase):
    """The systemd user service: no display at login, and a restart ends its whole cgroup."""

    def test_the_service_takes_the_sessions_display_and_starts_terminals_outside_its_cgroup(self):
        import subprocess
        from claudish import handoff
        shown = subprocess.CompletedProcess([], 0, stdout="HOME=/home/u\nDISPLAY=:0\nWAYLAND_DISPLAY=wayland-0\n")
        on_path = lambda name: "/usr/bin/" + name if name in ("xterm", "systemd-run", "claude") else None
        env = {"INVOCATION_ID": "abc", "PATH": "/usr/bin:/bin"}
        with patch("platform.system", return_value="Linux"), patch.dict(os.environ, env, clear=True), \
                patch("subprocess.run", return_value=shown) as asked, patch("shutil.which", side_effect=on_path), \
                patch("subprocess.Popen") as started:
            started.return_value.wait.return_value = 0  # the terminal opened its window
            self.assertTrue(handoff.launch(["claude", "{note}"], "/tmp/note.md"))
            self.assertEqual((os.environ.get("DISPLAY"), os.environ.get("WAYLAND_DISPLAY")), (":0", "wayland-0"))
        self.assertEqual(asked.call_args.args[0], ["systemctl", "--user", "show-environment"])
        argv = started.call_args.args[0]
        self.assertEqual(argv[:6], ["systemd-run", "--user", "--scope", "--quiet", "--collect", "--"])
        self.assertEqual(argv[6:8], ["xterm", "-e"])
        self.assertEqual(started.call_args.kwargs["env"]["DISPLAY"], ":0")

    def test_outside_systemd_nothing_is_asked_and_nothing_wraps(self):
        from claudish import children
        with patch("platform.system", return_value="Linux"), patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True), \
                patch("subprocess.run") as asked:
            children.session_display()
        asked.assert_not_called()
