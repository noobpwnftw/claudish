"""`claudish serve` at login: a model that cannot be set up leaves the input method running."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish import __main__ as cli
from claudish.model import Rewriter


class ServeTests(unittest.TestCase):
    def test_without_the_anthropic_sdk_the_service_runs_with_no_model_and_says_why(self):
        served = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "config.json")
            path.write_text('{"profile": "claude", "profiles": {"claude": {"backend": "claude"}}}')
            with patch.object(sys, "argv", ["claudish", "serve", "--config", str(path)]), \
                    patch.object(Rewriter, "from_settings", side_effect=ImportError("no anthropic")), \
                    patch.object(cli, "run_service", lambda rewriter, *rest: served.append(rewriter)), \
                    patch("sys.stderr"):
                cli.main()  # no SystemExit: a login service would start it again and again
        self.assertEqual(served[0].backend, "none")
        self.assertIn("Anthropic SDK", served[0].unavailable)
        self.assertIsNone(served[0].problem)  # the config reads: the settings window does not lock


if __name__ == "__main__":
    unittest.main()
