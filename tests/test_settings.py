import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from claudish import config, keys, settings
from claudish.model import Rewriter
from claudish.server import make_server


class Home(unittest.TestCase):
    """A config directory of its own, and no key in the environment."""

    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        environment = patch.dict(os.environ, {"XDG_CONFIG_HOME": home.name})
        environment.start()
        self.addCleanup(environment.stop)
        for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            os.environ.pop(name, None)
        if sys.platform == "darwin":  # never the real Keychain
            store = patch.object(keys, "stored", return_value=None)
            store.start()
            self.addCleanup(store.stop)
        self.path = config.default_path()

    def written(self):
        return json.loads(self.path.read_text(encoding="utf-8"))


class SettingsTests(Home):
    def test_before_any_config_it_shows_the_starter_and_writes_nothing(self):
        state = settings.state()
        self.assertEqual((state["choice"], state["key"], state["tone"]), ("claude", "missing", "corporate"))
        self.assertEqual([tone["name"] for tone in state["tones"]][:1], ["corporate"])
        self.assertFalse(self.path.exists())

    def test_a_tone_goes_to_every_profile_the_window_manages_and_corporate_clears_it(self):
        settings.apply({"tone": "critic"})
        profiles = self.written()["profiles"]
        self.assertEqual({profiles[n].get("tone") for n in ("claude", "ollama", "local")}, {"critic"})
        self.assertNotIn("tone", profiles["agent"])  # not the window's
        self.assertTrue(self.path.with_name("templates.json").is_file())  # the starter's, as init writes it
        state = settings.apply({"tone": "plain and friendly"})
        self.assertEqual((state["tone"], state["own_words"]), ("plain and friendly", True))
        settings.apply({"tone": "corporate"})
        self.assertFalse(any("tone" in p for p in self.written()["profiles"].values()))

    def test_claude_code_for_a_claude_subscription(self):
        with patch.object(settings, "claude_code", return_value=None):
            self.assertEqual(settings.state()["claude_code"], settings.NO_CLAUDE_CODE)
            with self.assertRaisesRegex(ValueError, "claude was not found"):  # not switched to what cannot answer
                settings.apply({"choice": "claude-code"})
        self.assertFalse(self.path.exists())
        with patch.object(settings, "claude_code", return_value="/opt/claude/bin/claude"):
            state = settings.apply({"choice": "claude-code", "tone": "critic"})
        self.assertEqual((state["choice"], state["claude_code"]), ("claude-code", None))
        profile = self.written()["profiles"]["claude-code"]
        # The full path: a login service may not have the shell's PATH.
        self.assertEqual((profile["command"], profile["model"]), (["/opt/claude/bin/claude"], "haiku"))
        self.assertEqual(profile["tone"], "critic")
        name, resolved, _, _ = config.resolve()
        self.assertEqual((name, resolved["backend"]), ("claude-code", "claude-code"))  # kept running (claudish/warm.py)

    def test_codex_for_a_chatgpt_subscription(self):
        with patch.object(settings, "codex", return_value=None):
            self.assertEqual(settings.state()["codex"], settings.NO_CODEX)
            with self.assertRaisesRegex(ValueError, "codex was not found"):  # not switched to what cannot answer
                settings.apply({"choice": "codex"})
        self.assertFalse(self.path.exists())
        with patch.object(settings, "codex", return_value="/opt/codex/bin/codex"):
            state = settings.apply({"choice": "codex"})
        self.assertEqual((state["choice"], state["codex"]), ("codex", None))
        profile = self.written()["profiles"]["codex"]
        # The full path: a login service may not have the shell's PATH.
        self.assertEqual((profile["command"], profile["model"]), (["/opt/codex/bin/codex"], "gpt-6-luna"))
        name, resolved, _, _ = config.resolve()
        self.assertEqual((name, resolved["backend"]), ("codex", "codex"))  # kept running (claudish/warm.py)

    def test_reselecting_a_subscription_keeps_its_model_and_custom_settings(self):
        for choice, finder in (("claude-code", "claude_code"), ("codex", "codex")):
            with self.subTest(choice=choice), patch.object(settings, finder, return_value="/new/" + choice):
                settings.apply({"choice": choice})
                data = self.written()
                data["profiles"][choice].update(model="chosen-model", timeout=42, tone="critic", read_terminal=False)
                self.path.write_text(json.dumps(data))
                settings.apply({"choice": "claude"})
                settings.apply({"choice": choice})
                profile = self.written()["profiles"][choice]
                self.assertEqual(profile["command"], ["/new/" + choice])
                self.assertEqual((profile["model"], profile["timeout"], profile["tone"], profile["read_terminal"]),
                                 ("chosen-model", 42, "critic", False))

    def test_the_extension_copy_is_the_command_not_a_helper_beside_it(self):
        with tempfile.TemporaryDirectory() as home:
            folder = Path(home, ".vscode-server/extensions/openai.chatgpt-26.1/bin/linux-aarch64")
            folder.mkdir(parents=True)
            for name in ("codex-code-mode-host", "codex"):
                Path(folder, name).write_text("")
                Path(folder, name).chmod(0o755)
            with patch.object(Path, "home", return_value=Path(home)), patch("shutil.which", return_value=None):
                self.assertEqual(settings.codex(), str(folder / "codex"))

    def test_the_newest_extension_copy_comes_first(self):
        self.assertGreater(settings.version_order("/x/openai.chatgpt-26.1021.2/codex"),
                           settings.version_order("/x/openai.chatgpt-26.999.9/codex"))

    def test_a_model_server_on_this_computer(self):
        with patch.object(settings, "check_server", return_value="nothing answers at http://127.0.0.1:1234"):
            with self.assertRaisesRegex(ValueError, "nothing answers"):  # not switched to a server that is not there
                settings.apply({"server": {"url": "http://127.0.0.1:1234/", "model": "gemma-4"}, "choice": "server"})
        self.assertFalse(self.path.exists())
        with patch.object(settings, "check_server", return_value=None):
            state = settings.apply({"server": {"url": "http://127.0.0.1:1234/", "model": "gemma-4"}, "choice": "server"})
        self.assertEqual((state["choice"], state["server"]), ("server", {"url": "http://127.0.0.1:1234", "model": "gemma-4", "key": "missing"}))
        self.assertEqual(self.written()["profile"], "ollama")
        self.assertEqual(config.resolve()[1]["model_url"], "http://127.0.0.1:1234")
        for server in ({"url": "localhost:1234", "model": "x"}, {"url": "http://127.0.0.1:1234", "model": " "}):
            with self.assertRaises(ValueError):
                settings.apply({"server": server})

    @unittest.skipIf(sys.platform == "darwin", "the Keychain on macOS")
    def test_another_model_api_with_its_key_saved_for_its_address_only(self):
        sent = []

        def models(url, key=None):
            sent.append(key)
            return ["gpt-5-mini"] if key == "sk-good" else settings.UNAUTHORIZED
        with patch.object(settings, "server_models", models):
            with self.assertRaisesRegex(ValueError, "wants an API key"):
                settings.apply({"server": {"url": "https://api.example.com", "model": "", "key": "sk-bad"},
                                "choice": "server"})
            self.assertIsNone(keys.server_key("https://api.example.com"))  # refused: not saved
            state = settings.apply({"server": {"url": "https://api.example.com/", "model": "", "key": "sk-good"},
                                    "choice": "server"})
        self.assertEqual(state["server"]["model"], "gpt-5-mini")  # the API's only model
        self.assertEqual(keys.server_key("https://api.example.com"), "sk-good")
        self.assertIsNone(keys.server_key("https://elsewhere.example.com"))
        self.assertNotIn("sk-good", self.path.read_text())  # never in the config
        from claudish.model import Rewriter
        rewriter = Rewriter.from_settings(config.resolve()[1])
        self.assertEqual(rewriter.api_key, "sk-good")  # the backend sends it

    def test_a_key_anthropic_refuses_is_not_saved(self):
        with patch.object(settings, "check_key", return_value="Anthropic did not accept that key"), \
                patch.object(keys, "store") as store:
            with self.assertRaisesRegex(ValueError, "did not accept"):
                settings.apply({"key": "sk-ant-wrong"})
        store.assert_not_called()

    @unittest.skipIf(sys.platform == "darwin", "the Keychain on macOS")
    def test_an_accepted_key_is_saved_for_this_user_only_and_never_in_the_config(self):
        with patch.object(settings, "check_key", return_value=None):
            state = settings.apply({"key": " sk-ant-good "})
        self.assertEqual((state["key"], keys.stored()), ("saved", "sk-ant-good"))
        self.assertEqual(stat.S_IMODE(keys.key_file("anthropic").stat().st_mode), 0o600)
        written = self.path.read_text()  # with no config yet, the key makes Claude the model
        self.assertEqual(json.loads(written)["profile"], "claude")
        self.assertNotIn("sk-ant-good", written)
        self.assertEqual(config.resolve()[1]["backend"], "claude")
        with self.assertRaises(ValueError):
            settings.apply({"key": "sk-ant one two"})

    def test_only_the_windows_settings(self):
        for changes in ({"backend": "rules"}, {"choice": "agent"}, {"tone": "two\nlines"}):
            with self.assertRaises(ValueError):
                settings.apply(changes)


class ServiceTests(Home):
    """The window's requests over HTTP: token-gated, and the service takes the change up at once."""

    def setUp(self):
        super().setUp()
        self.builds = []

        def reload():
            self.builds.append(config.resolve())
            return Rewriter("rules", tone=self.builds[-1][1].get("tone"))
        self.server_reload = [reload]  # a test can swap in one that fails
        self.server = make_server(Rewriter("rules"), 0, reload=lambda: self.server_reload[0](), config_path=self.path)
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.opener = build_opener(ProxyHandler({}))

    def call(self, path, body=None, token=True, origin=None, settings=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Claudish-Token"] = self.server.token
        if settings:
            headers["X-Claudish-Settings"] = settings
        if origin:
            headers["Origin"] = origin
        request = Request("http://127.0.0.1:%d%s" % (self.server.server_port, path),
                          json.dumps(body).encode() if body is not None else None, headers)
        try:
            with self.opener.open(request, timeout=10) as response:
                raw = response.read()
                return response.status, json.loads(raw) if response.headers.get_content_type() == "application/json" else raw
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def test_a_hand_edit_of_the_config_is_taken_up_at_the_next_request(self):
        import os
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"profile": "p", "profiles": {"p": {"backend": "rules", "tone": "bard"}}}))
        os.utime(self.path, ns=(1, 1))  # a change the folder's stamp sees, whatever the clock
        self.assertEqual(self.call("/health")[0], 200)
        self.assertEqual(self.builds[-1][1]["tone"], "bard")
        count = len(self.builds)
        self.call("/health")
        self.assertEqual(len(self.builds), count)  # unchanged: not rebuilt
        self.path.write_text("{not json")  # a broken edit leaves the service as it was
        os.utime(self.path, ns=(2, 2))
        self.server_reload[0] = lambda: (_ for _ in ()).throw(ValueError("bad config"))
        self.assertEqual(self.call("/health")[0], 200)

    def test_the_page_is_public_its_settings_are_not(self):
        status, page = self.call("/settings", token=False)
        self.assertEqual(status, 200)
        self.assertIn(b"cd_AI Settings", page)
        self.assertEqual(self.call("/settings/state", token=False)[0], 403)
        self.assertEqual(self.call("/settings", {"tone": "bard"}, token=False)[0], 403)
        self.assertEqual(self.call("/settings", {"tone": "bard"}, origin="http://evil.example")[0], 403)
        self.assertFalse(self.path.exists())

    def test_a_change_is_written_and_taken_up_by_the_next_request(self):
        status, state = self.call("/settings", {"tone": "bard"})
        self.assertEqual((status, state["tone"], state["service"]["backend"]), (200, "bard", "rules"))
        self.assertEqual(len(self.builds), 1)  # built again from the config just written
        self.assertEqual(self.builds[0][1]["tone"], "bard")
        status, state = self.call("/settings/state")
        self.assertEqual((status, state["tone"]), (200, "bard"))

    def test_the_page_gets_a_ticket_good_once_for_settings_only(self):
        status, ticket = self.call("/settings/ticket", {})
        self.assertEqual(status, 200)
        self.assertEqual(self.call("/settings/ticket", {}, token=False)[0], 403)  # only with the service token
        status, session = self.call("/settings/session", {"ticket": ticket["ticket"]}, token=False)
        self.assertEqual(status, 200)
        self.assertEqual(self.call("/settings/session", {"ticket": ticket["ticket"]}, token=False)[0], 403)  # once
        self.assertEqual(self.call("/settings/state", token=False, settings=session["token"])[0], 200)
        self.assertEqual(self.call("/recent", token=False, settings=session["token"])[0], 403)  # settings only

    def test_a_change_the_service_cannot_use_is_undone(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(config.STARTER))
        before = self.path.read_bytes()

        def broken():
            raise ValueError("environment variable NOPE is not set")
        self.server_reload[0] = broken
        status, answer = self.call("/settings", {"tone": "bard"})
        self.assertEqual(status, 400)
        self.assertIn("nothing changed", answer["error"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_a_slow_model_change_keeps_a_concurrent_tone_change(self):
        from concurrent.futures import ThreadPoolExecutor, TimeoutError
        config.write_starter()
        self.call("/health")  # take up the initial config before either window saves
        checking, proceed = threading.Event(), threading.Event()

        def check_server(*args, **kwargs):
            checking.set()
            if not proceed.wait(1):
                raise RuntimeError("the model check was not released")
            return None

        with patch.object(settings, "check_server", check_server), \
                patch.object(settings, "server_models", return_value=["rig-model"]), \
                ThreadPoolExecutor(max_workers=2) as workers:
            model = workers.submit(self.call, "/settings", {
                "choice": "server", "server": {"url": "http://127.0.0.1:1234", "model": "rig-model"}})
            try:
                self.assertTrue(checking.wait(1), "the model check did not start")
                tone = workers.submit(self.call, "/settings", {"tone": "bard"})
                try:
                    tone.result(timeout=0.1)
                except TimeoutError:
                    pass  # a save may wait for the first window's model check
            finally:
                proceed.set()
            self.assertEqual(model.result(timeout=1)[0], 200)
            self.assertEqual(tone.result(timeout=1)[0], 200)
        written = self.written()
        self.assertEqual(written["profile"], "ollama")
        self.assertEqual(written["profiles"]["ollama"]["model"], "rig-model")
        self.assertEqual(written["profiles"]["ollama"].get("tone"), "bard")
        self.assertEqual(self.call("/settings/state")[1]["tone"], "bard")

    def test_a_refused_change_says_why_and_changes_nothing(self):
        status, answer = self.call("/settings", {"server": {"url": "nope", "model": "x"}})
        self.assertEqual(status, 400)
        self.assertIn("http://", answer["error"])
        self.assertEqual(self.builds, [])


class OpenTests(unittest.TestCase):
    def test_a_starting_service_is_waited_for_until_its_token_is_written(self):
        """The service listens before it writes its new token: the first ask may carry the old one."""
        from claudish import __main__ as cli, client
        refused = HTTPError("http://127.0.0.1:18765/settings/ticket", 403, "Forbidden", {}, None)
        with patch.object(sys, "argv", ["claudish", "settings", "--first", "--print"]), \
                patch.object(client, "read_token", side_effect=["old", "new", "new"]), \
                patch.object(client, "settings_url", side_effect=[refused, "http://x/settings#ticket=t"]), \
                patch("builtins.print") as shown:
            cli.main()
        shown.assert_called_once_with("http://x/settings#ticket=t&first=1")


if __name__ == "__main__":
    unittest.main()
