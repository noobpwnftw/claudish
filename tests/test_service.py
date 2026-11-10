import os
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
    def test_the_service_reads_the_config_folder_setup_used(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/home/u/my config"}):
            unit, plist = service.systemd_unit(["claudish", "serve"]), service.launchd_plist(["claudish", "serve"])
        self.assertIn("Environment='XDG_CONFIG_HOME=/home/u/my config'\n", unit)
        self.assertIn("<key>XDG_CONFIG_HOME</key><string>/home/u/my config</string>", plist)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XDG_CONFIG_HOME", None)
            self.assertNotIn("XDG_CONFIG_HOME", service.systemd_unit(["claudish", "serve"]))
            self.assertNotIn("EnvironmentVariables", service.launchd_plist(["claudish", "serve"]))

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
        self.assertEqual(plist["ProcessType"], "Interactive")  # the input method waits on it from the first key

    def test_an_installed_package_runs_its_module(self):
        """Without the checkout's scripts/ (the Windows installer's Python): `python -m claudish serve`."""
        with tempfile.TemporaryDirectory() as directory, patch.object(service, "ROOT", Path(directory)):
            self.assertEqual(service.command(["--profile", "x"]),
                             [sys.executable, "-m", "claudish", "serve", "--profile", "x"])
        self.assertEqual(service.command([])[1:], [str(service.ROOT / "scripts" / "serve.py")])

    def test_inside_the_macos_bundle_cd_ai_starts_itself_through_its_launcher(self):
        """The bundle's bare Python needs the PYTHONHOME the launcher sets, which its children don't
        get (platforms/macos/main.py): the service and the agent's text box run the launcher."""
        launcher = "/Users/u/Library/Input Methods/Claudish.app/Contents/MacOS/Claudish"
        self.assertEqual(service.itself("textbox-mcp"), [sys.executable, "-m", "claudish", "textbox-mcp"])
        with patch.object(sys, "frozen", "macosx_app", create=True), patch.dict(os.environ, {"EXECUTABLEPATH": launcher}):
            self.assertEqual(service.itself("textbox-mcp"), [launcher, "textbox-mcp"])
            self.assertEqual(service.command(["--port", "1"]), [launcher, "serve", "--port", "1"])

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
        argv = ["claudish", "service", "install", "--dry-run", "--", "--backend", "rules"]
        with patch.object(sys, "argv", argv), patch.object(service, "run", return_value=0) as run:
            with self.assertRaises(SystemExit):
                cli.main()
        run.assert_called_once_with("install", ["--backend", "rules"], True)

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
            self.assertTrue(commands and all(c[0] == tool for c in commands), system)


    def test_the_unit_goes_where_systemd_reads_it(self):
        """An XDG_CONFIG_HOME exported in a shell is not the systemd user manager's: the unit goes
        in ~/.config (and passes the variable on to the service)."""
        with patch.dict("os.environ", {"XDG_CONFIG_HOME": "/elsewhere"}), \
                patch.object(Path, "home", return_value=Path("/home/u")):
            self.assertEqual(service.paths()["Linux"], Path("/home/u/.config/systemd/user/claudish.service"))

    def test_uninstall_says_what_it_could_not_do(self):
        from subprocess import CompletedProcess
        results = iter([CompletedProcess([], 1, "", "Failed to connect to bus: No medium found"),
                        CompletedProcess([], 1, "", "Failed to connect to bus: No medium found")])
        with tempfile.TemporaryDirectory() as directory, \
                patch("claudish.service.platform.system", return_value="Linux"), \
                patch.object(Path, "home", return_value=Path(directory)), \
                patch("claudish.service.subprocess.run", side_effect=lambda *a, **k: next(results)), \
                patch("builtins.print") as shown:
            with self.assertRaisesRegex(SystemExit, "reload systemd failed: Failed to connect to bus"):
                service.run("uninstall")
        lines = [call.args[0] for call in shown.call_args_list]
        self.assertIn("stop and disable it: not done (Failed to connect to bus: No medium found)", lines)
        self.assertNotIn("stop and disable it: done", lines)

    def test_macos_loads_the_agent_once_the_old_one_has_ended(self):
        """Bootstrap right after bootout fails ("5: Input/output error", 4 of 5 on the Mac VM) and
        nothing runs until the next login: it waits until launchd no longer has the old one."""
        from subprocess import CompletedProcess
        calls, printed = [], iter([0, 0, 113])
        def run(argv, **kwargs):
            calls.append(argv[:2])
            return CompletedProcess(argv, next(printed) if argv[1] == "print" else 0, "", "")
        with tempfile.TemporaryDirectory() as directory, \
                patch("claudish.service.platform.system", return_value="Darwin"), \
                patch("claudish.service.os.getuid", create=True, return_value=501), \
                patch.object(Path, "home", return_value=Path(directory)), \
                patch("claudish.service.time.sleep"), \
                patch("claudish.service.subprocess.run", side_effect=run), patch("builtins.print"):
            service.run("install", extra=["--backend", "rules"])
        self.assertEqual(calls, [["launchctl", "bootout"]] + [["launchctl", "print"]] * 3 + [["launchctl", "bootstrap"]])

    def test_accounts_with_names_in_other_scripts_get_their_own_tasks(self):
        names = []
        for user in ("张三", "李四", "Mei Lin"):
            with patch.dict("os.environ", {"USERNAME": user, "USERDOMAIN": "PC"}):
                names.append(service.task_name())
        self.assertEqual(len(set(names)), 3)
        self.assertEqual(names[2], "claudish-Mei_Lin")  # an ASCII name keeps the name it had

    def test_windows_logon_task_is_this_accounts_own(self):
        """A machine-wide "claudish" task was taken by whoever installed first; another account's
        install could not replace it, so its service never started at login (Windows VM)."""
        with patch("claudish.service.platform.system", return_value="Windows"), \
                patch.dict("os.environ", {"USERNAME": "Mei Lin"}):
            steps = service.plan("install", extra=["--backend", "rules"])
        names = [payload[payload.index("/tn") + 1] for _, kind, payload in steps if kind in ("run", "stop")]
        self.assertEqual(names, ["claudish-Mei_Lin"] * 3)  # this account's own, never a shared one
        self.assertEqual([kind for _, kind, _ in steps][-2:], ["stop", "run"])  # a running one ends first


class NoSystemdTests(unittest.TestCase):
    def test_without_a_systemd_user_manager_nothing_is_written_and_serve_is_named(self):
        with tempfile.TemporaryDirectory() as home, patch.object(Path, "home", return_value=Path(home)), \
                patch("claudish.service.platform.system", return_value="Linux"), \
                patch("claudish.service.systemd_user", return_value=False):
            with self.assertRaises(SystemExit) as stopped:
                service.run("install")
            self.assertIn("claudish serve", str(stopped.exception))
            self.assertFalse(service.paths()["Linux"].exists())  # no unit that looks installed
            self.assertEqual(service.managed()[0], "skip")



if __name__ == "__main__":
    unittest.main()
