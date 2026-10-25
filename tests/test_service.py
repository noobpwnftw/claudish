import plistlib
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree
from unittest.mock import patch

from claudish import service


class ServiceDefinitionTests(unittest.TestCase):
    def test_systemd_unit_quotes_the_command(self):
        argv = ["/opt/py 3/python", "-m", "claudish", "serve", "--profile", "my profile"]
        unit = service.systemd_unit(argv)
        exec_line = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
        self.assertEqual(shlex.split(exec_line[len("ExecStart="):]), argv)
        self.assertIn("WantedBy=default.target", unit)

    def test_launchd_plist_is_a_valid_plist(self):
        argv = ["/usr/bin/python3", "-m", "claudish", "serve", "--profile", "a&b"]
        plist = plistlib.loads(service.launchd_plist(argv).encode())
        self.assertEqual(plist["ProgramArguments"], argv)
        self.assertTrue(plist["RunAtLoad"])
        self.assertEqual(plist["KeepAlive"], {"SuccessfulExit": False})  # crashes restart; "already running" does not

    def test_an_installed_package_runs_its_module(self):
        """Without the checkout's scripts/ (the Windows installer's Python): `python -m claudish serve`."""
        with tempfile.TemporaryDirectory() as directory, patch.object(service, "ROOT", Path(directory)):
            self.assertEqual(service.command(False, ["--profile", "x"]),
                             [sys.executable, "-m", "claudish", "serve", "--profile", "x"])
        self.assertEqual(service.command(False, [])[1:], [str(service.ROOT / "scripts" / "serve.py")])

    def test_windows_task_prefers_pythonw(self):
        with tempfile.TemporaryDirectory() as directory:
            python, pythonw = Path(directory, "python.exe"), Path(directory, "pythonw.exe")
            python.write_text(""), pythonw.write_text("")
            with patch.dict("os.environ", {"USERDOMAIN": "PC", "USERNAME": "mei"}):
                task = ElementTree.fromstring(service.windows_task([str(python), "-m", "claudish", "serve"])
                                              .replace('encoding="UTF-16"', ""))
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        self.assertEqual(task.find("t:Actions/t:Exec/t:Command", ns).text, str(pythonw))
        self.assertEqual(task.find("t:Actions/t:Exec/t:Arguments", ns).text, "-m claudish serve")
        # A standard account may only create a task for its own logon.
        self.assertEqual(task.find("t:Triggers/t:LogonTrigger/t:UserId", ns).text, "PC\\mei")
        self.assertEqual(task.find("t:Settings/t:ExecutionTimeLimit", ns).text, "PT0S")


class SafetyTests(unittest.TestCase):
    """A dry run must not run anything or write anything; the CLI must not swallow --dry-run."""

    def test_cli_keeps_flags_before_the_separator(self):
        from claudish import __main__ as cli
        argv = ["claudish", "service", "install", "--local", "--dry-run", "--", "--backend", "rules"]
        with patch.object(sys, "argv", argv), patch.object(service, "run", return_value=0) as run:
            with self.assertRaises(SystemExit):
                cli.main()
        run.assert_called_once_with("install", True, ["--backend", "rules"], True)  # local, then dry run

    def test_dry_run_runs_and_writes_nothing_on_every_os(self):
        for system in ("Linux", "Windows", "Darwin"):
            with tempfile.TemporaryDirectory() as directory, \
                    patch("claudish.service.platform.system", return_value=system), \
                    patch.object(Path, "home", return_value=Path(directory)), \
                    patch.dict("os.environ", {"XDG_CONFIG_HOME": str(Path(directory, ".config"))}), \
                    patch("claudish.service.os.getuid", create=True, return_value=501), \
                    patch("claudish.service.subprocess.run", side_effect=AssertionError("ran a command")), \
                    patch("builtins.print"):
                for action in ("install", "uninstall"):
                    self.assertEqual(service.run(action, extra=["--backend", "rules"], dry_run=True), 0)
                self.assertEqual(list(Path(directory).rglob("*")), [], system)

    def test_plans_name_the_right_service_manager(self):
        for system, tool in (("Linux", "systemctl"), ("Windows", "schtasks"), ("Darwin", "launchctl")):
            with patch("claudish.service.platform.system", return_value=system), \
                    patch("claudish.service.os.getuid", create=True, return_value=501):
                steps = service.plan("install", extra=["--backend", "rules"])
            commands = [payload for _, kind, payload in steps if kind == "run"]
            self.assertTrue(all(c[0] == tool for c in commands), system)


    def test_windows_logon_task_is_this_accounts_own(self):
        """A machine-wide "claudish" task was taken by whoever installed first; another account's
        install could not replace it, so its service never started at login (Windows VM)."""
        with patch("claudish.service.platform.system", return_value="Windows"), \
                patch.dict("os.environ", {"USERNAME": "Mei Lin"}):
            steps = service.plan("install", extra=["--backend", "rules"])
        names = [payload[payload.index("/tn") + 1] for _, kind, payload in steps if kind in ("run", "stop")]
        self.assertEqual(names, ["claudish", "claudish-Mei_Lin", "claudish-Mei_Lin"])  # the old shared one goes first
        self.assertEqual(steps[0][1], "stop")  # another account's: it may not be ours to delete


if __name__ == "__main__":
    unittest.main()
