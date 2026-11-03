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

    def test_the_tone_is_the_files_for_every_profile_and_corporate_clears_it(self):
        settings.apply({"tone": "critic"})
        data = self.written()
        self.assertEqual(data["tone"], "critic")  # once, for every profile
        self.assertFalse(any("tone" in p for p in data["profiles"].values()))
        for name in data["profiles"]:
            self.assertEqual(config.resolve(self.path, profile=name)[1]["tone"], "critic")
        self.assertTrue(self.path.with_name("templates.json").is_file())  # the starter's, as init writes it
        state = settings.apply({"tone": "plain and friendly"})
        self.assertEqual((state["tone"], state["own_words"]), ("plain and friendly", True))
        settings.apply({"tone": "corporate"})
        self.assertNotIn("tone", self.written())

    def test_a_tone_is_changed_where_the_profile_in_use_takes_it(self):
        settings.apply({"tone": "corporate"})  # the starter config
        data = self.written()
        data["profiles"]["agent"] = {"backend": "command", "command": ["cat"], "tone": "proofread"}
        data["profile"] = "agent"
        self.path.write_text(json.dumps(data))
        self.assertEqual(settings.state()["tone"], "proofread")  # the one in use: the profile's own
        self.assertEqual(settings.apply({"tone": "bard"})["tone"], "bard")
        self.assertEqual(self.written()["profiles"]["agent"]["tone"], "bard")  # its own, not the file's
        self.assertNotIn("tone", self.written())
        settings.apply({"choice": "claude"})
        self.assertEqual(settings.apply({"tone": "critic"})["tone"], "critic")
        self.assertEqual((self.written()["tone"], self.written()["profiles"]["agent"]["tone"]), ("critic", "bard"))

    def test_a_config_that_does_not_read_is_said(self):
        # 0.3.1's starter running Claude Code: it reads, but the Claude the window switches to does not.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"profile": "claude-code", "profiles": {
            "claude": {"backend": "claude", "claude_model": "claude-opus-5-5"},
            "claude-code": {"backend": "claude-code", "command": ["/old/claude"], "model": "haiku"}}}))
        with self.assertRaisesRegex(ValueError, "unknown keys claude_model .*claudish init"):
            config.resolve(self.path, profile="claude")
        state = settings.state()
        self.assertEqual((state["choice"], state["config_problem"], state["config_locked"]),
                         ("claude-code", "profile 'claude': unknown keys claude_model", False))
        data = json.loads(self.path.read_text())
        data["profile"] = "claude"  # the one in use: nothing the window changes would be used
        self.path.write_text(json.dumps(data))
        self.assertTrue(settings.state()["config_locked"])
        self.path.write_text("{not json")  # the window still shows
        self.assertTrue(settings.state()["config_problem"].startswith("config.json does not read"))
        self.assertTrue(settings.state()["config_locked"])
        self.path.write_text('{"profile": ["claude"], "profiles": {"claude": {}}}')
        self.assertIn("profiles", settings.state()["config_problem"])
        self.path.unlink()
        config.write_starter()  # `claudish init`
        self.assertEqual((settings.state()["config_problem"], settings.state()["config_locked"]), (None, False))

    def test_a_server_that_refuses_says_how(self):
        self.assertEqual(settings.server_problem("https://api.openai.com/v1", 404),
                         "https://api.openai.com/v1 answered 404 to https://api.openai.com/v1/v1/models "
                         "(cd_AI adds /v1 itself: the address without it)")
        self.assertEqual(settings.server_problem("http://h:1", 500), "http://h:1 answered 500 to http://h:1/v1/models")

    def test_a_tone_of_your_own_templates_is_listed_by_name(self):
        config.write_starter()  # its templates.json has "mine"
        state = settings.apply({"tone": "mine"})
        self.assertEqual((state["tone"], state["own_words"]), ("mine", False))
        self.assertIn("mine", [tone["name"] for tone in state["tones"]])

    def test_the_model_server_in_use_is_checked_whatever_its_profiles_name(self):
        config.write_starter(profile="local")
        with patch.object(settings, "server_models", return_value=None) as asked:
            state = settings.state()
        asked.assert_called_once_with("http://127.0.0.1:18766")
        self.assertEqual((state["choice"], state["server_problem"]), ("local", "nothing answers at http://127.0.0.1:18766"))

    def test_model_names_the_claude_model(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"profiles": {"claude": {"backend": "claude", "model": "claude-sonnet-5-5"}}}))
        self.assertEqual(config.resolve(self.path)[1]["model"], "claude-sonnet-5-5")

    def test_claudish_key_says_why_a_refused_key_is_not_saved(self):
        from claudish.__main__ import main
        with patch.object(sys, "argv", ["claudish", "key"]), patch("getpass.getpass", return_value="sk-ant-bad"), \
                patch.object(settings, "accepted_key", side_effect=ValueError("Anthropic did not accept the key")):
            with self.assertRaises(SystemExit) as ended:
                main()
        self.assertEqual(ended.exception.code, "Nothing saved: Anthropic did not accept the key.")

    def test_keys_of_older_configs_are_refused_by_name(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for key in ("claude_model", "max_tokens", "hosted"):
            self.path.write_text(json.dumps({"profiles": {"claude": {"backend": "claude", key: 1}}}))
            with self.assertRaisesRegex(ValueError, "unknown keys " + key):
                config.resolve(self.path)

    def test_the_key_that_asks_is_saved_beside_the_profile(self):
        self.assertEqual(settings.apply({"tone": "corporate"})["summon"], "Shift+Enter")
        self.assertEqual(settings.apply({"summon": "Enter"})["summon"], "Enter")
        self.assertEqual(self.written()["keys"], {"summon": "Enter"})
        self.assertEqual(config.resolve(self.path)[1]["summon"], "Enter")
        settings.apply({"summon": "Shift+Enter"})
        self.assertNotIn("keys", self.written())  # the default: nothing written
        with self.assertRaises(ValueError):
            settings.apply({"summon": "Ctrl+Enter"})

    def test_hints_are_saved_only_when_off(self):
        self.assertIs(settings.apply({"tone": "corporate"})["hints"], True)
        self.assertIs(settings.apply({"hints": False})["hints"], False)
        self.assertIs(self.written()["hints"], False)
        self.assertIs(config.resolve(self.path)[1]["hints"], False)
        settings.apply({"hints": True})
        self.assertNotIn("hints", self.written())
        with self.assertRaises(ValueError):
            settings.apply({"hints": "off"})

    def test_claude_code_for_a_claude_subscription(self):
        with patch.object(settings, "claude_code", return_value=None):
            self.assertEqual(settings.state()["claude_code"], settings.NO_CLAUDE_CODE)
            with self.assertRaisesRegex(ValueError, "claude command was not found"):  # not switched to what cannot answer
                settings.apply({"choice": "claude-code"})
        self.assertFalse(self.path.exists())
        with patch.object(settings, "claude_code", return_value="/opt/claude/bin/claude"):
            state = settings.apply({"choice": "claude-code", "tone": "critic"})
        self.assertEqual((state["choice"], state["claude_code"]), ("claude-code", None))
        profile = self.written()["profiles"]["claude-code"]
        # The full path: a login service may not have the shell's PATH.
        self.assertEqual((profile["command"], profile["model"]), (["/opt/claude/bin/claude"], "haiku"))
        self.assertEqual(self.written()["tone"], "critic")
        name, resolved, _, _ = config.resolve()
        self.assertEqual((name, resolved["backend"]), ("claude-code", "claude-code"))  # kept running (claudish/warm.py)

    def test_a_hand_written_config_without_templates_takes_a_starter_profile(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"profile": "mine", "profiles": {"mine": {"backend": "rules"}}}), encoding="utf-8")
        with patch.object(settings, "claude_code", return_value="/opt/claude/bin/claude"):
            settings.apply({"choice": "claude-code"})
        name, resolved, _, _ = config.resolve()  # its templates.json is written beside it
        self.assertEqual((name, resolved["backend"]), ("claude-code", "claude-code"))
        self.assertTrue(self.path.with_name("templates.json").is_file())

    def test_codex_for_a_chatgpt_subscription(self):
        with patch.object(settings, "codex", return_value=None):
            self.assertEqual(settings.state()["codex"], settings.NO_CODEX)
            with self.assertRaisesRegex(ValueError, "codex command was not found"):  # not switched to what cannot answer
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
        where = state["server"].pop("key_where")  # its own file (or the Keychain), not Claude's
        if sys.platform != "darwin":  # both are in the Keychain there
            self.assertNotEqual(where, state["key_where"])
        self.assertEqual((state["choice"], state["server"]), ("server", {"url": "http://127.0.0.1:1234", "model": "gemma-4", "key": "missing"}))
        self.assertEqual(self.written()["profile"], "server")
        self.assertEqual(config.resolve()[1]["model_url"], "http://127.0.0.1:1234")
        for server in ({"url": "localhost:1234", "model": "x"}, {"url": "http://127.0.0.1:1234", "model": " "}):
            with self.assertRaises(ValueError):
                settings.apply({"server": server})

    @unittest.skipIf(sys.platform == "darwin", "the Keychain on macOS")
    def test_a_key_with_a_stray_space_a_hand_edit_meanwhile_and_a_bad_request_save_nothing_wrong(self):
        sent = []

        def models(url, key=None):
            sent.append(key)
            return ["m1"] if key == "sk-good" else settings.UNAUTHORIZED
        with patch.object(settings, "server_models", models):
            settings.apply({"server": {"url": "https://api.example.com", "model": "m1", "key": "sk-good "},
                            "choice": "server"})  # the key as pasted, with a space after it
            self.assertNotIn("sk-good ", sent)  # checked as it is saved: stripped
            # Another setting refused: the server key is not saved either.
            with self.assertRaises(ValueError):
                settings.apply({"server": {"url": "https://api.example.com", "model": "m1", "key": "sk-other"},
                                "summon": "bad"})
            self.assertEqual(keys.server_key("https://api.example.com"), "sk-good")

            def edited_meanwhile(url, key=None):  # the check takes seconds; config.json is edited by hand
                data = json.loads(self.path.read_text())
                data["hints"] = False
                self.path.write_text(json.dumps(data))
                os.utime(self.path, ns=(1, 1))  # a different time, whatever the clock's resolution
                return ["m1"]
        with patch.object(settings, "server_models", edited_meanwhile):
            with self.assertRaisesRegex(ValueError, "changed while"):
                settings.apply({"server": {"url": "https://api.example.com", "model": "m1"}, "choice": "server",
                                "tone": "critic"})
        self.assertIs(self.written()["hints"], False)  # the edit by hand stays
        self.assertNotIn("critic", self.path.read_text())
        self.assertIn("plain letter", settings.server_problem("http://x", settings.KEY_CHARACTERS))
        self.assertIn("not with a list of models", settings.server_problem("http://x", settings.NOT_MODELS))

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

        self.pinned = None  # a service started with --profile, or the local model's

        def reload():
            self.builds.append(config.resolve(profile=self.pinned))
            built = Rewriter("rules", tone=self.builds[-1][1].get("tone"))
            built.profile = self.builds[-1][0]
            return built
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

    def test_a_templates_file_in_a_folder_of_its_own_is_watched(self):
        import os
        words = self.path.parent / "words" / "t.json"
        words.parent.mkdir(parents=True)
        words.write_text("{}")
        self.path.write_text(json.dumps({"profile": "p", "profiles": {"p": {"backend": "rules", "templates": "words/t.json"}}}))
        self.call("/health")
        count = len(self.builds)
        os.utime(words, ns=(3, 3))  # only the templates file changed
        self.call("/health")
        self.assertEqual(len(self.builds), count + 1)

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

    def test_a_service_started_with_its_own_profile_does_not_take_another(self):
        config.write_starter(profile="local")
        self.pinned = "local"
        status, answer = self.call("/settings", {"choice": "claude"})
        self.assertEqual(status, 400)
        self.assertIn("runs the 'local' profile it was started with", answer["error"])
        self.assertEqual(self.written()["profile"], "local")
        self.assertEqual(self.call("/settings", {"tone": "bard"})[0], 200)  # the rest still applies

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

    def test_a_key_saved_with_a_change_that_is_undone_is_put_back_too(self):
        if sys.platform == "darwin":
            self.skipTest("the key files of Linux and Windows; never the real Keychain")
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(config.STARTER))
        self.server_reload[0] = lambda: (_ for _ in ()).throw(ValueError("environment variable NOPE is not set"))
        with patch.object(settings, "accepted_key", side_effect=lambda key: key):
            for earlier in (None, "sk-ant-earlier"):
                keys.forget()
                if earlier:
                    keys.store(earlier)
                status, answer = self.call("/settings", {"key": "sk-ant-new"})
                self.assertEqual(status, 400)
                self.assertIn("nothing changed", answer["error"])
                self.assertEqual(keys.stored(), earlier)  # not the new one

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
        self.assertEqual(written["profile"], "server")
        self.assertEqual(written["profiles"]["server"]["model"], "rig-model")
        self.assertEqual(written.get("tone"), "bard")
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


class ProxyTests(unittest.TestCase):
    def test_a_hosted_api_is_checked_through_the_proxy_rewrites_use(self):
        from claudish.model import opener_for

        def proxies(url):
            return [h.proxies for h in opener_for(url).handlers if isinstance(h, ProxyHandler)]
        with patch.dict(os.environ, {"https_proxy": "http://proxy.example:3128"}):
            self.assertEqual(proxies("https://api.openai.com"), [{"https": "http://proxy.example:3128"}])
            for url in ("http://127.0.0.1:8080", "http://localhost:8080", "http://[::1]:8080"):
                self.assertFalse(any(proxies(url)), url)  # none, or an empty one


class CliPlacesTests(unittest.TestCase):
    def test_an_nvm_install_is_found_newest_first_and_runs_with_its_node(self):
        from claudish import warm
        with tempfile.TemporaryDirectory() as home:
            for version in ("v18.20.1", "v22.3.0"):
                folder = Path(home, ".nvm/versions/node", version, "bin")
                folder.mkdir(parents=True)
                (folder / "claude").write_text("#!/usr/bin/env node\n")
                (folder / "claude").chmod(0o755)
            with patch("shutil.which", return_value=None), patch.object(Path, "home", return_value=Path(home)):
                found = settings.command_path("claude", ".vscode*/none/claude*")
            self.assertEqual(found, str(Path(home, ".nvm/versions/node/v22.3.0/bin/claude")))
            with patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
                self.assertEqual(warm.with_own_folder(found)["PATH"], str(Path(found).parent) + ":/usr/bin:/bin")
                self.assertIsNone(warm.with_own_folder("/usr/bin/claude"))  # already on PATH
