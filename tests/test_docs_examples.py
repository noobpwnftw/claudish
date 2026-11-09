"""Every JSON example in the docs loads as cd_AI loads it: a config (each profile resolved and
built), a context provider, or a templates file. An example that no longer loads is a doc to fix."""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish import config, modes
from claudish.context import Context
from claudish.model import Rewriter

ROOT = Path(__file__).resolve().parents[1]
FENCE = "`" * 3
DOCS = ("docs/configuration.md", "README.md", "docs/using.md", "docs/install.md")


def examples():
    for name in DOCS:
        text = (ROOT / name).read_text(encoding="utf-8")
        for block in re.findall(FENCE + r"json\n(.*?)" + FENCE, text, re.S):
            yield "%s:%d" % (name, text[:text.index(block)].count("\n") + 1), block


class DocsExamplesTests(unittest.TestCase):
    def test_every_example_loads(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest('MCP examples need the MCP SDK: pip install "claudish-ime[mcp]"')
        found = 0
        for where, block in examples():
            found += 1
            with self.subTest(example=where), tempfile.TemporaryDirectory() as home, \
                    patch.dict(os.environ, {"XDG_CONFIG_HOME": home}):
                data = json.loads(block)
                if "profiles" in data:
                    path = Path(home, "claudish", "config.json")
                    path.parent.mkdir(parents=True)
                    data.setdefault("profile", next(iter(data["profiles"])))  # a fragment: its first profile in use
                    path.write_text(json.dumps(data))
                    for profile in data["profiles"]:
                        _, settings, templates, context = config.resolve(path, profile)
                        Rewriter.from_settings(settings, templates, context, profile)
                elif data.get("type"):
                    Context([data])
                else:
                    path = Path(home, "templates.json")
                    path.write_text(json.dumps(data))
                    modes.load(path)
        self.assertGreater(found, 10)


if __name__ == "__main__":
    unittest.main()
