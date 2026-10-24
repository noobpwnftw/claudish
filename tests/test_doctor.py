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
        self.assertEqual(stale["IBus search path"][0], "warn")  # set up: the next login takes it up, not a failure
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
        self.root = Path(directory.name)  # the installer's folder: <app>\\python, <app>\\PIME
        (self.root / "PIME/python/input_methods/claudish").mkdir(parents=True)
        (self.root / "python").mkdir()

    def run_checks(self, pipes):
        with patch.object(sys, "executable", str(self.root / "python" / "python.exe")), \
                patch("claudish.doctor.os.listdir", return_value=pipes):
            return by_name(doctor.check_ime_windows())

    def test_installed_and_its_launcher_serving_beside_a_pime(self):
        results = self.run_checks(["Docker\\PIME\\Launcher", "Docker\\cd_AI\\Launcher"])
        self.assertEqual({name: status for name, (status, _) in results.items()}, {"Input method": "ok", "Launcher": "ok"})

    def test_a_pime_launcher_is_not_cd_ais(self):
        results = self.run_checks(["Docker\\PIME\\Launcher"])  # PIME's own, beside cd_AI
        self.assertEqual(results["Launcher"][0], "fail")

    def test_not_installed(self):
        with patch.object(sys, "executable", "/nowhere/python/python.exe"), \
                patch.dict(os.environ, {"ProgramFiles": str(self.root / "elsewhere")}):
            self.assertEqual(by_name(doctor.check_ime_windows())["Input method"][0], "fail")


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


class ModelServerChecks(unittest.TestCase):
    """An OpenAI-compatible server: asked with its saved key; loading and a refused key say so."""

    def check(self, error=None, key="sk-saved"):
        from urllib.error import HTTPError
        sent = {}

        def fetch(url, timeout=2, key=None):
            sent["key"] = key
            if error:
                raise HTTPError(url, error, "", {}, None)
            return {"data": []}
        settings = {"backend": "openai", "model_url": "https://api.example.com", "api_key_env": None}
        with patch.object(doctor, "fetch_json", fetch), patch("claudish.keys.server_key", return_value=key):
            status, detail, _ = doctor.check_backend({"settings": settings})
        return status, detail, sent["key"]

    def test_the_saved_key_is_sent(self):
        self.assertEqual(self.check()[0::2], ("ok", "sk-saved"))

    def test_loading_and_a_refused_key_are_named(self):
        self.assertEqual(self.check(503)[0], "warn")
        status, detail, _ = self.check(401)
        self.assertEqual(status, "fail")
        self.assertIn("did not accept the key", detail)


class TypedCommandTests(unittest.TestCase):
    """Hints name the command that runs here: `claudish` on PATH, else this Python with -m."""

    def test_on_path_or_not(self):
        import os
        from claudish import service
        script = os.path.join(os.path.dirname(sys.executable), "claudish")
        with patch("shutil.which", return_value=script):
            self.assertEqual(service.as_typed("run `claudish settings`"), "run `claudish settings`")
        with patch("shutil.which", return_value=None):
            self.assertEqual(service.as_typed("run `claudish settings`"), "run `%s -m claudish settings`" % sys.executable)


class ClaudeKeyChecks(unittest.TestCase):
    """No Claude key: with Claude Code installed, the fix names the settings' Claude Code choice."""

    def check(self, found):
        settings = {"backend": "claude", "claude_model": "claude-opus-5-5"}
        with patch.dict(os.environ, {}, clear=False), patch("claudish.keys.stored", return_value=None), \
                patch.object(Path, "home", return_value=Path("/nonexistent-home")), \
                patch("claudish.settings.claude_code", return_value=found):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
            return doctor.check_backend({"settings": settings})

    def test_the_fix_names_claude_code_when_it_is_installed(self):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.skipTest("needs the Anthropic SDK")
        self.assertIn("pick Claude Code", self.check("/usr/bin/claude")[2])
        self.assertNotIn("Claude Code", self.check(None)[2])


if __name__ == "__main__":
    unittest.main()
