import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish import config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        patcher = patch.dict("os.environ", {"XDG_CONFIG_HOME": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, data, name="claudish/config.json"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_no_file_means_defaults_plus_flags(self):
        name, settings, templates, _ = config.resolve(overrides={"backend": "rules", "timeout": None})
        self.assertIsNone(name)
        self.assertEqual((settings["backend"], settings["timeout"]), ("rules", 3))
        self.assertIsNone(templates)

    def test_profile_selection_and_precedence(self):
        self.write({"modes": {"rewrite": {"system": "Be grand.", "examples": []}}}, "claudish/grand.json")
        self.write({"profile": "ollama", "profiles": {
            "ollama": {"backend": "openai", "model_url": "http://127.0.0.1:11434", "model": "qwen2.5:7b",
                       "templates": "grand.json"},
            "claude": {"backend": "claude", "claude_model": "claude-haiku-5-5"}}})
        name, settings, templates, _ = config.resolve()  # found at $XDG_CONFIG_HOME/claudish/config.json
        self.assertEqual((name, settings["model"]), ("ollama", "qwen2.5:7b"))
        self.assertEqual(templates["modes"]["rewrite"]["system"], "Be grand.")  # relative to the config file
        name, settings, _, _ = config.resolve(profile="claude", overrides={"claude_model": "claude-opus-5-5"})
        self.assertEqual((name, settings["backend"], settings["claude_model"]),
                         ("claude", "claude", "claude-opus-5-5"))

    def test_invalid_configs_fail_with_clear_messages(self):
        for profile, message in [({"api_key": "sk-secret"}, "api_key_env"),
                                 ({"modle": "typo"}, "unknown keys modle"),
                                 ({"timeout": "3"}, "timeout has the wrong type"),
                                 ({"timeout": True}, "timeout has the wrong type"),
                                 ({"backend": "gpt"}, "backend must be one of"),
                                 ({"backend": "command"}, "needs \"command\""),
                                 ({"backend": "command", "command": "claude -p"}, "command has the wrong type"),
                                 ({"hosted": "no"}, "hosted has the wrong type")]:
            path = self.write({"profiles": {"p": profile}}, "other.json")
            with self.assertRaisesRegex(ValueError, message):
                config.resolve(path)
        path = self.write({"profiles": {"p": {}}}, "other.json")
        with self.assertRaisesRegex(ValueError, "'missing' is not in"):
            config.resolve(path, "missing")
        with self.assertRaisesRegex(ValueError, "profiles"):
            config.resolve(self.write([], "other.json"))
        with self.assertRaisesRegex(ValueError, "needs a config file"):
            config.resolve(profile="claude")

    def test_secret_values_never_appear_in_errors(self):
        path = self.write({"profiles": {"p": {"api_key": "sk-ant-very-secret"}}}, "other.json")
        with self.assertRaises(ValueError) as error:
            config.resolve(path)
        self.assertNotIn("sk-ant-very-secret", str(error.exception))


    def test_the_starter_brings_its_templates_to_change(self):
        from claudish.model import Rewriter
        path = config.write_starter()
        self.assertTrue(path.with_name("templates.json").is_file())  # beside it, for the profiles to read
        data = json.loads(path.read_text(encoding="utf-8"))
        data["profiles"]["claude"]["tone"] = "mine"
        path.write_text(json.dumps(data), encoding="utf-8")
        _, settings, templates, _ = config.resolve()
        mine = Rewriter.from_settings(dict(settings, backend="rules"), templates)
        self.assertIn("pirate", mine.modes["rewrite"]["system"])  # the starter's own tone
        self.assertIn("corporate slop", mine.modes["instruct"]["system"])  # what it does not name stays cd_AI's

    def test_starter_config_is_valid_and_never_overwrites(self):
        path = config.write_starter()
        self.assertEqual(path, self.root / "claudish/config.json")
        for name in config.STARTER["profiles"]:
            _, settings, _, _ = config.resolve(path, name)
            self.assertEqual(settings["backend"], config.STARTER["profiles"][name]["backend"])
        self.assertEqual(config.resolve()[0], "claude")  # a frontier model with your key; no local one ships
        path.write_text('{"profiles": {"mine": {}}}', encoding="utf-8")
        with self.assertRaises(FileExistsError):
            config.write_starter()
        self.assertIn("mine", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
