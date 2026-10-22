import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish import fix

ROOT = Path(__file__).resolve().parents[1]


class FixTests(unittest.TestCase):
    def test_typo_distance_and_candidates(self):
        self.assertEqual(fix.typo_distance("gti", "git"), 1)  # a swap is one edit
        self.assertEqual(fix.typo_distance("sl", "ls"), 1)
        self.assertEqual(fix.typo_distance("pyhton3", "python3"), 1)
        self.assertGreater(fix.typo_distance("ls", "docker"), 2)
        names = ["git", "gtf", "tic", "ls", "nl", "python3", "python", "docker"]
        self.assertEqual(fix.similar_programs("gti", names)[0], "git")
        self.assertEqual(fix.similar_programs("sl", names)[0], "ls")
        self.assertEqual(fix.similar_programs("pyhton3", names)[:2], ["python3", "python"])
        self.assertEqual(fix.similar_programs("zzzz", names), [])

    def test_describe_uses_only_local_facts(self):
        text = fix.describe("gti log --oneline", 127, names=["git", "gtf"], found=False)
        self.assertEqual(text, "Command: gti log --oneline\nExit status: 127\nNot found: gti\nSimilar programs: git, gtf")
        self.assertEqual(fix.describe("git psuh", 1, found=True), "Command: git psuh\nExit status: 1")
        self.assertNotIn("Directory", fix.describe("ls", 2, found=True))

    def test_clean_replies(self):
        self.assertEqual(fix.clean("```bash\ngit push\n```", "git psuh"), "git push")
        self.assertEqual(fix.clean("$ git push\nThis fixes the typo.", "git psuh"), "git push")
        self.assertEqual(fix.clean("`git push`", "git psuh"), "git push")
        self.assertIsNone(fix.clean('grep -r "TODO" .', "grep -r TODO ."))  # same words: no change
        self.assertIsNone(fix.clean("", "x"))
        self.assertTrue(fix.same_command("echo 'a b'", 'echo "a b"'))
        self.assertFalse(fix.same_command("grep -r 'TODO .'", "grep -r TODO ."))

    def test_state_file_and_hook_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state"
            path.write_text("127\n/home/u/src\ngti status", encoding="utf-8")
            self.assertEqual(fix.last_failure(path), (127, "/home/u/src", "gti status"))
            path.write_text("garbage", encoding="utf-8")
            self.assertIsNone(fix.last_failure(path))
            self.assertIsNone(fix.last_failure(Path(directory) / "missing"))
        for shell in fix.HOOKS:
            hook = fix.shell_hook(shell, "my-claudish")
            self.assertIn(str(fix.state_path()), hook)
            self.assertIn("my-claudish fix", hook)
            self.assertNotIn("eval -- \"$suggestion\"" if shell == "zsh" else "print -z", hook)

    def test_cli_fix_with_explicit_command(self):
        class Fake:
            def __init__(self, *args, **kwargs):
                self.prompt = args[7] if len(args) > 7 else kwargs.get("prompt")

            def rewrite(self, text):
                assert text.startswith("Command: git psuh origin main\nExit status: 1")
                return {"text": "git push origin main"}

        from claudish import __main__ as cli
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict("os.environ", {"XDG_CONFIG_HOME": directory}), \
                patch.object(cli, "Rewriter", Fake), \
                patch.object(sys, "argv", ["claudish", "fix", "--", "git", "psuh", "origin", "main"]), \
                patch("builtins.print") as printed:
            cli.main()
        printed.assert_called_once_with("git push origin main")

    @unittest.skipUnless(shutil.which("bash"), "needs bash")
    def test_bash_hook_parses_in_this_bash(self):
        result = subprocess.run(["bash", "-n"], input=fix.shell_hook("bash"), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("bash") and hasattr(os, "getuid"), "needs bash")
    def test_bash_hook_records_failures_privately_without_rerunning(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, XDG_RUNTIME_DIR=directory, HOME=directory)
            with patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}):
                hook, state = fix.shell_hook("bash", "true"), fix.state_path()
            rc = Path(directory) / "rc"
            rc.write_text("set -o history\n" + hook + "\n", encoding="utf-8")
            marker = Path(directory) / "ran"
            script = "touch %s; definitely-not-a-command-xyz --flag\ntrue\n" % marker
            subprocess.run(["bash", "--rcfile", str(rc), "-i"], input=script, text=True, env=environment,
                           capture_output=True, timeout=20)
            status, _, command = fix.last_failure(state)
            self.assertEqual((status, command), (127, "touch %s; definitely-not-a-command-xyz --flag" % marker))
            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)
            marker.unlink()  # The hook must not run the command again.
            subprocess.run(["bash", "--rcfile", str(rc), "-i"], input="true\n", text=True, env=environment,
                           capture_output=True, timeout=20)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
