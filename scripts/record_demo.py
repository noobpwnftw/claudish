"""Record docs/cd_AI.gif: the browser demo against a real model, "ok" with Tab and Tab, then an
instruction with Shift+Enter, its drafts, ↓ and Tab.

python scripts/record_demo.py --model-url http://127.0.0.1:18790 [--out docs/cd_AI.gif]

It starts its own service (a scratch config folder, port 18901), takes timed screenshots of the
demo's text box with Playwright's Chromium, and joins them into a GIF (run it with a Python that has
Playwright and Pillow, such as .tools/browser-venv).
"""
import argparse
import asyncio
import glob
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PORT = 18901


async def capture(chromium, url, folder):
    from playwright.async_api import async_playwright
    frames = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chromium)
        page = await browser.new_page(viewport={"width": 880, "height": 1200}, device_scale_factor=2)
        await page.goto(url)
        await page.wait_for_timeout(600)
        # Only the text box: the page's help line and samples below it are not part of the recording.
        await page.evaluate("document.querySelectorAll('#hint, #samples, footer').forEach((e) => e.style.visibility = 'hidden')")
        box = await page.locator("#editor").locator("xpath=..").bounding_box()
        clip = {"x": box["x"] - 14, "y": box["y"] - 14, "width": box["width"] + 28, "height": 560}
        await page.click("#editor")

        async def shot(ms):
            path = folder / ("%02d.png" % len(frames))
            await page.screenshot(path=str(path), clip=clip)
            frames.append((path, ms))

        async def until(script):
            await page.wait_for_function(script, timeout=60000)

        async def typed(text, pause):
            for char in text:
                await page.keyboard.type(char)
                await page.wait_for_timeout(pause)

        await typed("ok", 120)
        await shot(1300)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(150)
        await shot(500)
        await until("() => (document.querySelector('#editor .k-panel') || {}).innerText?.includes('Rewrite')")
        await page.wait_for_timeout(250)
        await shot(2600)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(250)
        await shot(1300)
        await page.keyboard.press("Enter")  # nothing composed: a new line
        await typed("decline the offsite politely", 35)
        await page.wait_for_timeout(200)
        await shot(1400)
        await page.keyboard.press("Shift+Enter")
        await page.wait_for_timeout(200)
        await shot(700)
        await until("() => document.querySelectorAll('#editor .k-row').length > 1")
        await page.wait_for_timeout(250)
        await shot(2400)
        await page.keyboard.press("ArrowDown")
        await page.wait_for_timeout(200)
        await shot(1600)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(250)
        await shot(3000)
        await browser.close()
    return frames


def gif(frames, out):
    from PIL import Image
    images = [Image.open(path).convert("RGB") for path, _ in frames]
    images = [image.resize((image.width // 2, image.height // 2), Image.LANCZOS) for image in images]
    palette = images[-1].quantize(colors=96, method=Image.MEDIANCUT)
    quantized = [image.quantize(palette=palette, dither=Image.NONE) for image in images]
    quantized[0].save(out, save_all=True, append_images=quantized[1:], duration=[ms for _, ms in frames],
                      loop=0, optimize=True)
    print("wrote %s: %dx%d, %d frames, %d KB" % (out, *images[0].size, len(images), os.path.getsize(out) // 1024))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-url", required=True, help="An OpenAI-compatible server")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "cd_AI.gif")
    parser.add_argument("--chromium", help="Chromium executable for Playwright")
    args = parser.parse_args()
    chromium = args.chromium or next(iter(sorted(glob.glob(os.path.expanduser(
        "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))), None)
    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        service = subprocess.Popen([sys.executable, "-m", "claudish", "serve", "--model-url", args.model_url,
                                    "--port", str(PORT), "--timeout", "60"], cwd=ROOT,
                                   env=dict(os.environ, XDG_CONFIG_HOME=str(scratch)),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                try:
                    urlopen("http://127.0.0.1:%d/health" % PORT, timeout=1).close()
                    break
                except OSError:
                    time.sleep(0.25)
            frames = asyncio.run(capture(chromium, "http://127.0.0.1:%d/" % PORT, scratch))
            gif(frames, args.out)
        finally:
            service.terminate()
            service.wait(timeout=5)


if __name__ == "__main__":
    main()
