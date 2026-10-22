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
    def test_home_page_links_the_demo_and_its_install_prompt_is_real(self):
        import re
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            out = build_site(Path(directory) / "site")
            page = (out / "index.html").read_text(encoding="utf-8")
            demo = (out / "demo" / "index.html").read_text(encoding="utf-8")
            css = (out / "site.css").read_text(encoding="utf-8")
        self.assertIn('href="demo/"', page)
        self.assertNotIn('href="/', page)
        self.assertIn('class="wordmark" href="../"', demo)  # the demo links back home
        self.assertIn(':root[data-theme="dark"]{', css)  # the demo's tokens, both themes
        self.assertIn("Content-Security-Policy", page)
        prompt = re.search(r'<pre id="prompt-text">(.*?)</pre>', page, re.S).group(1)
        self.assertTrue(prompt.rstrip().endswith("Make no mistakes."))
        # Every command the prompt tells an agent to run must exist.
        for command in re.findall(r"`python -m claudish ([^`]+)`", prompt):
            words = command.split()
            usage = subprocess.run([sys.executable, "-m", "claudish", words[0], "--help"], cwd=str(ROOT),
                                   capture_output=True, text=True)
            self.assertEqual(usage.returncode, 0, command)
            for flag in (w for w in words[1:] if w.startswith("--")):
                self.assertIn(flag, usage.stdout, command)


if __name__ == "__main__":
    unittest.main()
