import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import start  # noqa: E402

ENDPOINT = "http://127.0.0.1:18766"


class LocalRewriterTests(unittest.TestCase):
    """start.py (and `service install`, which runs it) must use the profile's context, not ignore the config."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.config = Path(directory.name) / "claudish" / "config.json"
        p = patch.dict(os.environ, {"XDG_CONFIG_HOME": directory.name})
        p.start()
        self.addCleanup(p.stop)

    def write(self, data):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(json.dumps(data))
        (self.config.parent / "notes.md").write_text("Prefer short sentences.")

    def test_without_a_config_it_is_the_built_in_local_model(self):
        rewriter = start.local_rewriter(ENDPOINT)
        self.assertEqual((rewriter.backend, rewriter.endpoint, rewriter.profile, rewriter.context),
                         ("llama", ENDPOINT, None, None))

    def test_local_profile_brings_its_context_and_bindings_with_this_model(self):
        self.write({"profile": "claude", "profiles": {
            "claude": {"backend": "claude"},
            "local": {"backend": "llama", "model_url": "http://elsewhere:1", "timeout": 5,
                      "context": [{"type": "file", "path": "notes.md"}],
                      "bindings": [{"app": "code", "context": [{"type": "file", "path": "notes.md"}]}]}}})
        rewriter = start.local_rewriter(ENDPOINT)
        self.assertEqual((rewriter.profile, rewriter.endpoint, rewriter.timeout), ("local", ENDPOINT, 5))
        self.assertEqual(rewriter.context.providers[0].get(), "Prefer short sentences.")
        self.assertEqual(len(rewriter.bindings), 1)

    def test_a_hosted_profile_points_to_claudish_serve(self):
        self.write({"profiles": {"claude": {"backend": "claude"}}})
        with self.assertRaisesRegex(ValueError, "claudish serve --profile claude"):
            start.local_rewriter(ENDPOINT)
        with self.assertRaisesRegex(ValueError, "not in"):
            start.local_rewriter(ENDPOINT, "missing")


if __name__ == "__main__":
    unittest.main()
