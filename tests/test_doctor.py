import io
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish import doctor
from claudish.model import Rewriter
from claudish.server import make_server


def by_name(results):
    return {name: (status, fix) for name, status, _, fix in results}


@unittest.skipIf(os.name == "nt", "the IBus checks run on Linux; IBUS_COMPONENT_PATH is colon-separated")
class LinuxChecks(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        self.component = self.home / ".local/share/ibus/component/claudish.xml"
        engine = self.home / "engine.py"
        engine.write_text("")
        self.xml = '<exec>/usr/bin/python3 &quot;%s&quot; --ibus</exec>' % engine
        patches = [patch.object(Path, "home", return_value=self.home),
                   patch("claudish.doctor.shutil.which", return_value="/usr/bin/ibus-daemon"),
                   patch("claudish.doctor.subprocess.run",
                         return_value=subprocess.CompletedProcess([], 0, "  claudish - cd_AI", ""))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def run_checks(self, **env):
        with patch.dict(os.environ, env, clear=False):
            if "IBUS_COMPONENT_PATH" not in env:
                os.environ.pop("IBUS_COMPONENT_PATH", None)
            return by_name(doctor.check_ime_linux())

    def test_not_registered(self):
        status, fix = self.run_checks()["Input method"]
        self.assertEqual(status, "fail")
        self.assertIn("install.py", fix)

    def test_stale_session_then_healthy(self):
        self.component.parent.mkdir(parents=True)
        self.component.write_text(self.xml)
        (self.home / ".config/environment.d").mkdir(parents=True)
        (self.home / ".config/environment.d/90-claudish-ibus.conf").write_text("IBUS_COMPONENT_PATH=x\n")
        stale = self.run_checks(XDG_CONFIG_HOME=str(self.home / ".config"))
        self.assertEqual(stale["IBus search path"][0], "fail")
        self.assertIn("log out and back in", stale["IBus search path"][1])
        healthy = self.run_checks(IBUS_COMPONENT_PATH="/usr/share/ibus/component:%s" % self.component.parent)
        self.assertEqual({name: status for name, (status, _) in healthy.items()},
                         {"Input method": "ok", "IBus search path": "ok", "IBus engine": "ok"})

    def test_moved_checkout(self):
        self.component.parent.mkdir(parents=True)
        self.component.write_text('<exec>/usr/bin/python3 &quot;/gone/engine.py&quot; --ibus</exec>')
        self.assertEqual(self.run_checks()["Input method"][0], "fail")


class WindowsChecks(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "PIME/python/input_methods/claudish").mkdir(parents=True)
        (self.root / "PIME/python/textService.py").write_text("")
        (self.root / "Windows/SysWOW64").mkdir(parents=True)

    def run_checks(self, pipes, tasklist=""):
        env = {"ProgramFiles(x86)": str(self.root), "WINDIR": str(self.root / "Windows")}
        with patch.dict(os.environ, env), patch("claudish.doctor.platform.machine", return_value="ARM64"), \
                patch("claudish.doctor.os.listdir", return_value=pipes), \
                patch("claudish.doctor.subprocess.run", return_value=subprocess.CompletedProcess([], 0, tasklist, "")):
            return by_name(doctor.check_ime_windows())

    def test_arm64_without_x86_runtime_and_a_crashed_launcher(self):
        results = self.run_checks([], tasklist="PIMELauncher.exe   1896")
        self.assertEqual(results["x86 VC++ runtime"][0], "fail")
        self.assertIn("vc_redist.x86", results["x86 VC++ runtime"][1])
        self.assertEqual(results["PIME launcher"][0], "fail")

    def test_healthy(self):
        (self.root / "Windows/SysWOW64/vcruntime140.dll").write_text("")
        results = self.run_checks(["Docker\\PIME\\Launcher"])
        self.assertEqual({name: status for name, (status, _) in results.items()},
                         {"Input method": "ok", "x86 VC++ runtime": "ok", "PIME launcher": "ok"})


class GeneralChecks(unittest.TestCase):
    def test_ascii_marks_for_a_cp1252_console(self):
        with patch.object(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252")):
            self.assertEqual(doctor.marks()["ok"], "[ok]")
        with patch.object(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8")):
            self.assertEqual(doctor.marks()["ok"], "✓")

    def test_service_check_reports_the_running_service(self):
        server = make_server(Rewriter("rules"), 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            with patch.object(doctor, "SERVICE", "http://127.0.0.1:%d" % server.server_port):
                status, detail, _ = doctor.check_service({})
            self.assertEqual(status, "ok")
            self.assertIn("backend rules", detail)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        with patch.object(doctor, "SERVICE", "http://127.0.0.1:9"):
            self.assertEqual(doctor.check_service({})[0], "fail")


if __name__ == "__main__":
    unittest.main()
