import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from claudish import config, setup


class SetupTests(unittest.TestCase):
    """Every action is mocked: setup's real installs run only in the systemd container test."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        self.model = self.home / "models/model.gguf"
        self.llama = SimpleNamespace(installed=lambda: None, host=lambda: ("Linux", "arm64"), BUILD="b1",
                                     ASSETS={("Linux", "arm64", "cpu"): ("llama.tar.gz", 18 << 20, "x")},
                                     install=MagicMock())
        self.models = SimpleNamespace(target=lambda preset: self.model, PRESETS={"gemma": (0, 0, 0, 5154941280)},
                                      fetch=MagicMock())
        self.service_run = MagicMock(return_value=0)
        self.ime = MagicMock()
        self.managed = ("warn", "not managed")
        self.backend = ("fail", "the Anthropic SDK is not installed", 'pip install "claudish-ime[claude]"')
        patches = [
            patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.home / ".config"), "HOME": str(self.home)}),
            patch.object(Path, "home", return_value=self.home),
            patch("claudish.setup.platform.system", return_value="Linux"),
            patch("claudish.mcp_setup.platform.system", return_value="Linux"),
            patch.object(setup, "scripts", return_value=(self.llama, self.models)),
            patch("claudish.setup.shutil.which", return_value=None),
            patch.object(setup, "ROOT", self.home),
            patch("claudish.setup.doctor.check_ime_linux",
                  return_value=[("Input method", "fail", "not registered", "install.py")]),
            patch("claudish.setup.subprocess.run", self.ime),
            patch("claudish.setup.service.managed", side_effect=lambda: self.managed),
            patch("claudish.setup.service.run", self.service_run),
            patch("claudish.setup.doctor.fetch_json", side_effect=OSError("down")),
            patch("claudish.setup.doctor.main", return_value=0),
            patch("claudish.setup.doctor.check_backend", side_effect=lambda state: self.backend),
            patch.object(setup, "wait_for_service", return_value=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def states(self, profile=None):
        return {label: state for label, state, _, _ in setup.plan(profile)[1]}

    def quiet(self, *args, **kwargs):
        with redirect_stdout(io.StringIO()) as out:
            status = setup.run(*args, **kwargs)
        return status, out.getvalue()

    def test_fresh_machine_plans_everything_but_the_model_is_yours(self):
        self.assertEqual(self.states(), {"Config": "todo", "Tone": "done", "MCP servers": "skip", "Model": "manual",
                                         "Input method": "todo", "Starts at login": "todo"})
        _, out = self.quiet(yes=True)
        self.assertIn('Model needs you: pip install "claudish-ime[claude]"', out)
        self.service_run.assert_not_called()  # not at every login while it has no model
        self.assertIn("not yet: the model needs setting up first (Model)", out)

    def test_a_local_model_is_an_optional_profile(self):
        self.assertEqual(self.states("local"), {"Config": "todo", "Tone": "done", "MCP servers": "skip",
                                                "llama.cpp": "todo", "Model": "todo", "Input method": "todo",
                                                "Starts at login": "todo"})

    def test_tone_is_set_for_the_profile(self):
        status, out = self.quiet(yes=True, tone="fix")
        self.assertEqual(status, 0, out)
        _, settings, _, _ = config.resolve()
        self.assertEqual(settings["tone"], "fix")
        self.assertEqual(self.states()["Tone"], "done")  # the default profile keeps it

    def test_dry_run_changes_nothing(self):
        status, out = self.quiet(dry_run=True)
        self.assertEqual(status, 0)
        self.assertIn("nothing was changed", out)
        self.assertFalse(config.default_path().exists())
        for action in (self.llama.install, self.models.fetch, self.ime, self.service_run):
            action.assert_not_called()

    def test_yes_runs_each_step_once_then_doctor(self):
        status, out = self.quiet("local", yes=True)
        self.assertEqual(status, 0, out)
        self.assertTrue(config.default_path().is_file())
        self.llama.install.assert_called_once()
        self.models.fetch.assert_called_once()
        self.assertEqual(self.ime.call_args.args[0][1], str(self.home / "platforms/linux/install.py"))
        self.service_run.assert_called_once_with("install", local=True, extra=[])
        self.assertIn("Log out and back in", out)
        setup.doctor.main.assert_called_once()

    def test_declining_or_no_terminal_skips_the_step(self):
        with patch("builtins.input", side_effect=EOFError):
            _, out = self.quiet()
        self.assertFalse(config.default_path().exists())
        self.service_run.assert_not_called()
        self.assertIn("skipped", out)

    def test_done_steps_are_left_alone(self):
        config.write_starter()
        self.model.parent.mkdir(parents=True)
        self.model.write_text("")
        self.llama.installed = lambda: self.home / ".tools/llama-server"
        self.managed = ("ok", "systemd user unit (active)")
        self.backend = ("ok", "Claude via the Anthropic SDK", None)
        with patch("claudish.setup.doctor.check_ime_linux", return_value=[("Input method", "ok", "registered", None)]):
            self.assertEqual(set(self.states().values()) - {"skip"}, {"done"})

    def test_a_hosted_profile_downloads_nothing_and_runs_serve(self):
        config.write_starter()
        self.backend = ("ok", "Claude via the Anthropic SDK", None)
        states = self.states("claude")
        self.assertEqual(states["Model"], "done")
        self.assertNotIn("llama.cpp", states)
        self.quiet("claude", yes=True)
        self.service_run.assert_called_once_with("install", local=False, extra=["--profile", "claude"])

    def test_a_service_running_by_hand_is_not_doubled(self):
        with patch("claudish.setup.doctor.fetch_json", return_value={"backend": "llama"}):
            _, out = self.quiet(yes=True)
        self.service_run.assert_not_called()
        self.assertIn("already running outside the service manager", out)

    def test_mcp_servers_are_offered_once(self):
        desktop = self.home / ".config/Claude/claude_desktop_config.json"
        desktop.parent.mkdir(parents=True)
        desktop.write_text(json.dumps({"mcpServers": {"notes": {"command": "notes-mcp"}}}))
        self.assertEqual(self.states()["MCP servers"], "todo")
        self.quiet(yes=True)
        self.assertEqual(self.states()["MCP servers"], "done")

    def test_a_failing_step_does_not_stop_the_rest_but_no_service_without_a_model(self):
        self.models.fetch.side_effect = OSError("network down")
        _, out = self.quiet("local", yes=True)
        self.assertIn("failed: network down", out)
        self.ime.assert_called_once()  # later steps still run
        self.service_run.assert_not_called()
        self.assertIn("the model needs setting up first (Model)", out)
        self.assertEqual(config.resolve()[0], "local")  # the profile set up is the config's default


if __name__ == "__main__":
    unittest.main()
