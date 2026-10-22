"""Acceptance test for the static demo: the model runs in the page, with no inference server.

python tests/static_demo.py --model models/qwen2.5-0.5b-instruct-q4_k_m.gguf [--executable chromium]
Builds dist/demo, serves it with a plain static server (no COOP/COEP headers, like GitHub Pages), and
checks the isolation reload, model loading, rewrite, instruct mode, and that nothing calls a server.
"""
import argparse
import asyncio
import functools
import http.server
import shutil
import sys
import tempfile
import threading
from pathlib import Path

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_static_demo import build  # noqa: E402


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


async def check(url, executable, screenshots=None):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**({"executable_path": executable} if executable else {}))
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        await page.goto(url + "?model=model.gguf")
        await page.wait_for_function("() => self.crossOriginIsolated", timeout=15000)  # after one reload
        await page.locator("#load-model").click()
        await expect(page.locator("#model-strip.loading .model-progress")).to_be_visible(timeout=10000)
        await expect(page.locator("#model-strip.ready")).to_be_visible(timeout=120000)
        if screenshots:
            await page.screenshot(path=str(screenshots / "static-ready.png"))
        await page.locator("#draft").fill("This is very important.")
        await expect(page.locator("#accept")).to_be_enabled(timeout=60000)
        rewrite = await page.locator("#candidate").inner_text()
        assert rewrite.strip(), "empty rewrite"
        assert "IN THIS BROWSER" in await page.locator("#timing").inner_text()
        await page.locator("#draft").press("Tab")
        await expect(page.locator("#output")).to_have_value(rewrite)
        await page.get_by_role("radio", name="INSTRUCT").check()
        await page.locator("#draft").fill("thank the team for shipping the release")
        await page.locator("#draft").press("Enter")
        await expect(page.locator("#accept")).to_be_enabled(timeout=60000)
        draft = await page.locator("#candidate").inner_text()
        await page.locator("#draft").press("Enter")
        await expect(page.locator("#output")).to_have_value(rewrite + "\n\n" + draft)
        assert not any("/suggest" in u or "/health" in u for u in requests), "the static page called a server"
        assert not errors, errors
        await browser.close()
    print("Static demo passed: isolation, in-browser model, rewrite %r, instruct, no server calls" % rewrite)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, type=Path, help="Local GGUF served as model.gguf")
    parser.add_argument("--executable", help="Chromium executable for Playwright")
    parser.add_argument("--screenshots", type=Path, help="Save a screenshot of the ready state here")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        site = build(Path(directory) / "demo")
        (site / "model.gguf").symlink_to(args.model.resolve())
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            asyncio.run(check("http://127.0.0.1:%d/" % server.server_port, args.executable, args.screenshots))
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
