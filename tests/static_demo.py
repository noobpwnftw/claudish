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
        committed, window, keys = page.locator("#page"), page.locator("#candidates"), page.keyboard
        await page.locator("#editor").click()
        await keys.press("Shift")  # the demo opens in compose; a Shift tap: continue, keys straight in
        sample = "Thanks for the quick review on "  # the demo's own continue sample (demo.js SAMPLES)
        await keys.type(sample, delay=20)
        await expect(page.locator("#ghost")).not_to_be_empty(timeout=60000)
        assert "in this browser" in await page.locator("#timing").text_content()
        ghost = await page.locator("#ghost").text_content()
        await keys.press("Tab")
        await expect(committed).to_have_attribute("data-text", sample + ghost)
        # The owner's sequence: take, space, take, space. The template's example answers are never offered.
        from claudish import modes
        examples = {m["content"] for m in modes.defaults()["continue"]["examples"] if m["role"] == "assistant"}
        for _ in range(2):
            await keys.type(" ")
            await page.wait_for_timeout(2500)
            offered = await page.locator("#ghost").text_content()
            assert offered.strip() not in examples, offered
            assert not (await page.locator("#status").text_content()).strip(), "continue showed an error"
            if offered:
                await keys.press("Tab")
        await keys.press("Enter")
        await keys.press("Shift")  # compose
        before = await committed.get_attribute("data-text")
        await keys.type("This is very important.", delay=20)
        await keys.press("Tab")  # asks; the rewrite takes your words' place as it arrives
        await expect(page.locator("#candidates")).to_contain_text("Rewrite", timeout=60000)  # it waits in the panel
        rewrite = await page.locator("#candidates .k-body").text_content()  # the rewrite, in the panel
        assert rewrite.strip(), "empty rewrite"
        await keys.press("Tab")  # keeps it
        await expect(committed).to_have_attribute("data-text", before + rewrite)
        # still compose: Enter does it as an instruction
        await keys.type("thank the team for shipping the release", delay=10)
        await keys.press("Enter")  # sends
        await expect(window.locator(".k-row").first).to_be_visible(timeout=60000)  # the drafts
        draft = await window.locator(".k-row .k-text").first.text_content()
        await keys.press("Enter")  # a reflexive second Enter inserts nothing: Enter talks to the model
        await expect(committed).to_have_attribute("data-text", before + rewrite)
        await keys.press("Tab")  # Tab takes the model's text
        await expect(committed).to_have_attribute("data-text", before + rewrite + draft)
        # While the model runs, Remove stops it and deletes what the page stored (its files are open
        # while it runs), including anything an earlier download left.
        await page.evaluate("""async () => {
            const dir = await (await navigator.storage.getDirectory()).getDirectoryHandle('leftover', {create: true});
            const writable = await (await dir.getFileHandle('partial.bin', {create: true})).createWritable();
            await writable.write(new Uint8Array(1024));
            await writable.close(); }""")
        await page.locator("#remove-model").click()
        await expect(page.locator("#remove-model")).to_be_hidden(timeout=10000)
        await expect(page.locator("#status")).to_contain_text("Removed the model")
        assert not await page.evaluate("""async () => {
            for await (const _ of (await navigator.storage.getDirectory()).keys()) return true;
            return false; }"""), "something was left in storage after Remove"
        await page.reload()
        await page.wait_for_function("() => self.crossOriginIsolated", timeout=15000)
        await expect(page.locator("#remove-model")).to_be_hidden()
        assert not any("/suggest" in u or "/health" in u for u in requests), "the static page called a server"
        assert not errors, errors
        # A browser without room for the model runs it from memory and stores nothing.
        tight = await browser.new_page()
        await tight.add_init_script(
            "navigator.storage.estimate = async () => ({usage: 0, quota: 50 * 1024 * 1024})")
        await tight.goto(url + "?model=model.gguf")
        await tight.wait_for_function("() => self.crossOriginIsolated", timeout=15000)
        await tight.locator("#load-model").click()
        await expect(tight.locator("#model-strip.ready")).to_be_visible(timeout=120000)
        await expect(tight.locator("#model-copy")).to_contain_text("runs from memory")
        assert not await tight.evaluate("""async () => {
            const dir = await (await navigator.storage.getDirectory()).getDirectoryHandle('cache', {create: true});
            for await (const _ of dir.values()) return true;
            return false; }"""), "the model was written to storage"
        await browser.close()
    print("Static demo passed: isolation, in-browser model, continue %r, rewrite %r, instruct, stored and removed, "
          "runs from memory without room, no server calls" % (ghost, rewrite))


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
