import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_static_demo import MODEL_URL, build, build_site  # noqa: E402
from claudish import modes  # noqa: E402


class StaticDemoBuildTests(unittest.TestCase):
    def test_build_is_relative_in_browser_and_shares_the_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            site = build(Path(directory) / "demo")
            page = (site / "index.html").read_text(encoding="utf-8")
            self.assertNotIn('src="/', page)
            self.assertNotIn('href="/', page)
            self.assertIn('<meta name="claudish-backend" content="browser">', page)
            self.assertIn("Content-Security-Policy", page)
            self.assertIn('href="https://github.com/noobpwnftw/claudish"', page)
            for name in ("demo.js", "browser.js", "coi-sw.js", "theme.js", "demo.css"):
                self.assertTrue((site / name).is_file(), name)
            templates = json.loads((site / "templates.json").read_text(encoding="utf-8"))
            self.assertEqual(templates["model_url"], MODEL_URL)
            for name, spec in modes.defaults().items():
                self.assertEqual(templates["modes"][name]["system"], spec["system"])
                self.assertEqual(templates["modes"][name]["examples"], spec["examples"])


class SiteBuildTests(unittest.TestCase):
    def test_home_page_links_the_demo_and_its_recordings(self):
        import re
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            out = build_site(Path(directory) / "site")
            page = (out / "index.html").read_text(encoding="utf-8")
            demo = (out / "demo" / "index.html").read_text(encoding="utf-8")
            css = (out / "site.css").read_text(encoding="utf-8")
            recordings = {name: (out / name).is_file() for name in ("cd_AI.gif", "cd_AI-terminal.gif")}
        self.assertIn('href="demo/"', page)
        self.assertNotIn('href="/', page)
        self.assertIn('class="wordmark" href="../"', demo)  # the demo links back home
        self.assertIn(':root[data-theme="dark"]{', css)  # the demo's tokens, both themes
        self.assertIn("Content-Security-Policy", page)
        for name in ("cd_AI.gif", "cd_AI-terminal.gif"):
            self.assertIn('src="%s"' % name, page)
            self.assertTrue(recordings[name], name)


if __name__ == "__main__":
    unittest.main()
