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

    def test_a_switch_to_a_cli_profile_waits_for_its_cli(self):
        """Setup on a machine whose service runs: switched to codex, the closing doctor says whether
        the CLI is signed in, not "starting"."""
        config.write_starter()
        self.managed = ("ok", "systemd user unit (enabled)")
        self.backend = ("ok", "Codex (gpt-6-luna), kept running by the service", None)
        setup.wait_for_model.reset_mock()
        with patch("claudish.setup.doctor.fetch_json", return_value={"backend": "claude", "profile": "claude"}), \
                patch("claudish.setup.doctor.ours", return_value=True):
            self.quiet("codex", yes=True, skip=("input",))
        self.assertEqual(setup.wait_for_model.call_args_list[-1].args, (30,))

    def test_a_local_model_is_one_on_this_computer_by_any_loopback_name(self):
        for url in ("http://127.0.0.1:18766", "http://localhost:8080", "http://[::1]:18766"):
            self.assertTrue(setup.is_local({"backend": "llama", "model_url": url}), url)
        self.assertFalse(setup.is_local({"backend": "llama", "model_url": "http://10.0.0.2:8080"}))
        self.assertFalse(setup.is_local({"backend": "openai", "model_url": "http://127.0.0.1:18766"}))

    """Every action is mocked: setup's real installs run only in the systemd container test."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        self.model = self.home / "models/model.gguf"
        self.llama = SimpleNamespace(installed=lambda: None, host=lambda: ("Linux", "arm64"), BUILD="b1",
                                     ASSETS={("Linux", "arm64", "cpu"): ("llama.tar.gz", 18 << 20, "x")},
                                     install=MagicMock())
        self.llama.find_server = lambda: self.llama.installed() and str(self.llama.installed())
        self.models = SimpleNamespace(target=lambda preset: self.model, PRESETS={"gemma": (0, 0, 0, 5154941280)},
                                      fetch=MagicMock())
        self.service_run = MagicMock(return_value=0)
        self.ime = MagicMock()
        self.managed = ("warn", "not managed")
        self.backend = ("fail", "the Anthropic SDK is not installed", 'pip install -e ".[claude]"')
        patches = [
            patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.home / ".config"), "HOME": str(self.home)}),
            patch.object(Path, "home", return_value=self.home),
            patch("claudish.setup.platform.system", return_value="Linux"),
            patch("claudish.mcp_setup.platform.system", return_value="Linux"),
            patch.object(setup, "scripts", return_value=(self.llama, self.models)),
            patch.object(setup, "ROOT", self.home),
            patch("claudish.setup.doctor.check_ime_linux",
                  return_value=[("Input method", "fail", "not registered", "install.py")]),
            patch("claudish.setup.subprocess.run", self.ime),
            patch("claudish.setup.service.managed", side_effect=lambda: self.managed),
            patch("claudish.setup.service.elsewhere", side_effect=lambda: self.elsewhere),
            patch("claudish.setup.service.run", self.service_run),
            patch("claudish.setup.doctor.fetch_json", side_effect=OSError("down")),
            patch("claudish.setup.doctor.main", return_value=0),
            patch("claudish.setup.doctor.check_backend", side_effect=lambda state: self.backend),
            patch.object(setup, "wait_for_service", return_value=True),
            patch.object(setup, "wait_for_model", return_value=None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    elsewhere = None  # the registered service's checkout, when it is another one

    def test_a_service_running_another_checkout_is_not_done(self):
        self.managed = ("ok", "systemd user unit (enabled)")
        self.elsewhere = "/home/me/.local/share/claudish"
        with patch("claudish.setup.doctor.fetch_json", return_value={}), patch("claudish.setup.doctor.ours", return_value=True):
            self.assertEqual(self.states()["Starts at login"], "todo")
        self.elsewhere = None
        with patch("claudish.setup.doctor.fetch_json", return_value={}), patch("claudish.setup.doctor.ours", return_value=True):
            self.assertEqual(self.states()["Starts at login"], "done")

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
        self.assertIn('Model needs you: pip install -e ".[claude]"', out)
        self.service_run.assert_called_once()  # without a key too: the key goes in the settings it serves
        self.assertNotIn("not yet", out)

    def test_a_local_model_is_an_optional_profile(self):
        self.assertEqual(self.states("local"), {"Config": "todo", "Tone": "done", "MCP servers": "skip",
                                                "llama.cpp": "todo", "Model": "todo", "Local model": "todo",
                                                "Input method": "todo", "Starts at login": "todo"})

    def test_tone_is_set_for_the_profile(self):
        status, out = self.quiet(yes=True, tone="proofread")
        self.assertEqual(status, 0, out)
        _, settings, _, _ = config.resolve()
        self.assertEqual(settings["tone"], "proofread")
        self.assertEqual(self.states()["Tone"], "done")  # the default profile keeps it

    def test_the_first_run_asks_for_a_tone_once(self):
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=["proofread", "y", "y", "y", "y", "y"]):
            _, out = self.quiet()
        self.assertIn("Which tone?", out)
        self.assertEqual(config.resolve()[1]["tone"], "proofread")
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=["y"] * 6):
            _, out = self.quiet()
        self.assertNotIn("Which tone?", out)  # the profile has one now
        _, out = self.quiet(yes=True)
        self.assertNotIn("Which tone?", out)

    def test_an_update_asks_nothing_and_opens_no_settings(self):
        config.write_starter()  # installed before: running the install line again updates it
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=["y"] * 6), \
                patch.object(setup, "settings") as opened:
            _, out = self.quiet()
        self.assertNotIn("Which tone?", out)
        opened.assert_not_called()

    def test_without_the_download_helpers_the_local_model_is_set_up_by_hand(self):
        with patch.object(setup, "scripts", side_effect=ImportError("no scripts/ in this install")):
            steps = {label: (state, detail) for label, state, detail, _ in setup.plan("local")[1]}
        self.assertEqual(steps["Local model"], ("manual", "the local model is set up from a source checkout"))
        self.assertNotIn("llama.cpp", steps)

    def test_dry_run_changes_nothing(self):
        status, out = self.quiet(dry_run=True)
        self.assertEqual(status, 0)
        self.assertIn("nothing was changed", out)
        self.assertFalse(config.default_path().exists())
        for action in (self.llama.install, self.models.fetch, self.ime, self.service_run):
            action.assert_not_called()

    def test_yes_runs_each_step_once_then_doctor(self):
        self.llama.install.side_effect = lambda *args: setattr(self.llama, "installed", lambda: self.home / ".tools/llama-server")
        self.models.fetch.side_effect = lambda *args: self.model.parent.mkdir(parents=True) or self.model.write_text("")
        status, out = self.quiet("local", yes=True)
        self.assertEqual(status, 0, out)
        self.assertTrue(config.default_path().is_file())
        self.llama.install.assert_called_once()
        self.models.fetch.assert_called_once()
        self.assertEqual(self.ime.call_args.args[0][1], str(self.home / "platforms/linux/install.py"))
        self.service_run.assert_called_once_with("install", keep=True)
        data = json.loads(config.default_path().read_text())
        self.assertEqual(data["profile"], "local")  # the downloaded model runs from the profile, in use
        self.assertEqual(data["profiles"]["local"]["command"][:3], [str(self.home / ".tools/llama-server"), "-m", str(self.model)])
        self.assertIn("Log out and back in", out)
        setup.doctor.main.assert_called_once()

    def test_a_skipped_model_is_not_run_from_the_profile(self):
        self.llama.installed = lambda: self.home / ".tools/llama-server"
        _, out = self.quiet("local", yes=True, skip=["model"])
        self.assertIn("the model is not downloaded", out)
        data = json.loads(config.default_path().read_text())
        self.assertNotIn("command", data["profiles"].get("local", {}))  # the service would fail at every login

    def test_declining_or_no_terminal_skips_the_step(self):
        with patch("builtins.input", side_effect=EOFError):
            _, out = self.quiet()
        self.assertFalse(config.default_path().exists())
        self.service_run.assert_not_called()
        self.assertIn("skipped", out)

    def test_a_profile_asked_for_becomes_the_default_of_a_config_there_already(self):
        config.write_starter()  # an earlier install's, or the installer's: the default is "claude"
        self.assertEqual(self.states()["Config"], "done")
        self.assertEqual(self.states("claude")["Config"], "done")
        self.assertEqual(self.states("codex")["Config"], "todo")
        status, out = self.quiet(profile="codex", yes=True, skip=("service", "input", "model"))
        self.assertIn("make 'codex' the default profile", out)
        self.assertEqual(config.resolve()[0], "codex")  # what the service and doctor run
        self.assertEqual(self.states("codex")["Config"], "done")

    def test_a_tone_without_the_config_step_writes_the_profile_asked_for(self):
        status, out = self.quiet(profile="codex", yes=True, tone="proofread", skip=("config", "service", "input", "model"))
        self.assertEqual(status, 0, out)
        name, settings, _, _ = config.resolve()
        self.assertEqual((name, settings["tone"]), ("codex", "proofread"))

    def test_a_config_whose_templates_are_gone_is_said_not_a_traceback(self):
        config.write_starter(profile="claude")
        data = json.loads(config.default_path().read_text())
        data["profiles"]["claude"]["templates"] = "gone.json"
        config.default_path().write_text(json.dumps(data))
        status, out = self.quiet(dry_run=True)
        self.assertEqual(status, 2)
        self.assertIn("setup: ", out)

    def test_done_steps_are_left_alone(self):
        config.write_starter()
        self.model.parent.mkdir(parents=True)
        self.model.write_text("")
        self.llama.installed = lambda: self.home / ".tools/llama-server"
        self.managed = ("ok", "systemd user unit (enabled)")
        self.backend = ("ok", "Claude via the Anthropic SDK", None)
        with patch("claudish.setup.doctor.check_ime_linux", return_value=[("Input method", "ok", "registered", None)]), \
                patch("claudish.setup.doctor.fetch_json", return_value={"service": "cd_AI"}):
            self.assertEqual(set(self.states().values()) - {"skip"}, {"done"})

    def test_a_service_set_to_start_at_login_but_stopped_is_started(self):
        config.write_starter()
        self.managed = ("ok", "systemd user unit (enabled)")  # /health does not answer (setUp)
        self.backend = ("ok", "Claude via the Anthropic SDK", None)
        self.quiet("claude", yes=True)
        self.service_run.assert_called_once_with("install", keep=True)

    def test_a_hosted_profile_downloads_nothing_and_runs_serve(self):
        config.write_starter()
        self.backend = ("ok", "Claude via the Anthropic SDK", None)
        states = self.states("claude")
        self.assertEqual(states["Model"], "done")
        self.assertNotIn("llama.cpp", states)
        self.quiet("claude", yes=True)
        self.service_run.assert_called_once_with("install", keep=True)

    def test_a_service_running_by_hand_is_not_doubled(self):
        with patch("claudish.setup.doctor.fetch_json", return_value={"backend": "llama"}):
            _, out = self.quiet(yes=True)
        self.service_run.assert_not_called()
        self.assertIn("already running outside the service manager", out)

    def test_a_running_service_whose_unit_is_not_enabled_is_installed_again(self):
        """`systemctl --user disable` without --now: running, not starting at login, and no terminal
        to Ctrl+C in. Installing again enables it."""
        unit = self.home / ".config/systemd/user/claudish.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Unit]\n")
        self.managed = ("warn", "systemd user unit (disabled)")
        with patch("claudish.setup.doctor.fetch_json", return_value={"backend": "llama"}):
            _, out = self.quiet(yes=True)
        self.service_run.assert_called_once_with("install", keep=True)
        self.assertNotIn("outside the service manager", out)

    def test_an_input_method_ibus_cannot_see_is_set_up_again(self):
        with patch("claudish.setup.doctor.check_ime_linux", return_value=[
                ("Input method", "ok", "registered", None),
                ("IBus search path", "fail", "IBus cannot see Claudish", "install.py")]):
            self.assertEqual(self.states()["Input method"], "todo")

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

    def test_a_local_profile_becomes_the_default_only_when_its_model_runs(self):
        config.write_starter()  # a working config: the service runs its default meanwhile
        self.models.fetch.side_effect = OSError("network down")
        _, out = self.quiet("local", yes=True)
        self.assertNotIn("make 'local' the default", out)
        self.assertEqual(config.resolve()[0], "claude")  # not a server that is not there

    def test_no_service_when_the_local_model_step_failed(self):
        self.llama.installed = lambda variant=None: self.home / "llama-server"
        self.model.parent.mkdir(parents=True)
        self.model.write_bytes(b"x")
        with patch("claudish.warm.llama_command", side_effect=ValueError("bad server")):
            _, out = self.quiet("local", yes=True)
        self.assertIn("failed: bad server", out)
        self.service_run.assert_not_called()
        self.assertIn("the model needs setting up first (Local model)", out)

    def test_a_variant_asked_for_is_downloaded_and_run_when_another_is_there(self):
        cpu, vulkan = self.home / "llama-b1-cpu/llama-server", self.home / "llama-b1-vulkan/llama-server"
        self.llama.ASSETS[("Linux", "arm64", "vulkan")] = ("llama-vulkan.tar.gz", 20 << 20, "x")
        self.llama.installed = lambda variant=None: cpu if variant in (None, "cpu") else None
        self.assertEqual(self.states("local")["llama.cpp"], "done")
        self.assertEqual({label: state for label, state, _, _ in setup.plan("local", "vulkan")[1]}["llama.cpp"], "todo")
        self.llama.installed = lambda variant=None: vulkan if variant == "vulkan" else cpu
        data = json.loads(json.dumps(config.STARTER))
        data["profile"] = "local"
        data["profiles"]["local"]["command"] = [str(cpu), "-m", "model.gguf"]
        config.save(data)
        self.assertEqual(self.states("local")["Local model"], "done")  # no variant asked: the one it runs
        self.assertEqual({label: state for label, state, _, _ in setup.plan("local", "vulkan")[1]}["Local model"], "todo")

    def test_mcp_servers_imported_before_a_config_keep_the_profile_asked_for(self):
        desktop = self.home / ".config/Claude/claude_desktop_config.json"
        desktop.parent.mkdir(parents=True)
        desktop.write_text(json.dumps({"mcpServers": {"notes": {"command": "notes-mcp"}}}))
        self.quiet("codex", yes=True, skip=("config", "service", "input", "model"))
        self.assertEqual(config.resolve()[0], "codex")

    def test_a_subscription_cli_is_waited_for_so_doctor_says_its_sign_in(self):
        self.backend = ("ok", "claude found", None)
        _, out = self.quiet("claude-code", yes=True, skip=("input",))
        self.service_run.assert_called_once_with("install", keep=True)
        setup.wait_for_model.assert_called_once_with(30)

    def test_no_desktop_session_opens_no_text_browser(self):
        from claudish.client import open_browser
        with patch.dict(os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": ""}), \
                patch("platform.system", return_value="Linux"), patch("webbrowser.open") as opened:
            self.assertFalse(open_browser("http://127.0.0.1:18765/settings"))
        opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class LinuxInputMethodStepTests(unittest.TestCase):
    def step(self, *rows):
        with patch("claudish.setup.platform.system", return_value="Linux"), \
                patch("claudish.setup.doctor.check_ime_linux", return_value=list(rows)):
            return setup.step_ime()

    def test_doctors_failure_is_said_not_hidden_behind_registering(self):
        registered = ("Input method", "ok", "registered (x)", None)
        status, detail, fix = self.step(("Input framework", "fail", "apps send their keys to another input method "
                                         "(GTK_IM_MODULE=fcitx)", "pick IBus"), registered)
        self.assertEqual((status, fix), ("manual", "pick IBus"))
        self.assertIn("GTK_IM_MODULE=fcitx", detail)
        status, detail, _ = self.step(registered, ("IBus engine", "fail", "IBus is not running in this session", "KDE: …"))
        self.assertEqual(status, "manual")
        status, _, fix = self.step(registered, ("IBus search path", "fail", "this session does not read it",
                                                "sudo /usr/bin/python3 install.py --system, then log out and back in"))
        self.assertEqual(status, "manual")
        self.assertIn("--system", fix)

    def test_registering_is_offered_when_it_is_what_is_missing(self):
        self.assertEqual(self.step(("Input method", "fail", "the Claudish IBus component is not registered", "x"))[0], "todo")
        self.assertEqual(self.step(("Input method", "ok", "registered (x)", None),
                                   ("IBus search path", "fail", "does not include it", "install.py"))[0], "todo")
        self.assertEqual(self.step(("Input method", "ok", "registered (x)", None),
                                   ("IBus search path", "warn", "next login", "log out"))[0], "done")
        self.assertEqual(self.step(("Input method", "fail", "IBus is not installed", "sudo apt install ibus"))[0], "manual")


class WaitTests(unittest.TestCase):
    def test_no_service_answering_is_not_waited_for(self):
        from claudish import setup as real
        calls = []

        def down(*args, **kwargs):
            calls.append(1)
            raise ConnectionRefusedError()
        with patch.object(real.doctor, "fetch_json", down), patch.object(real.time, "sleep"):
            real.wait_for_model(120)
        self.assertEqual(len(calls), 3)  # not 120 s of asking
