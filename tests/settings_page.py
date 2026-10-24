"""The settings window's page in a real browser, against a service of its own in a throwaway config
directory (never yours). python tests/settings_page.py [--executable CHROMIUM] [--screenshots DIR]"""
import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def check(args, home, port):
    environment = dict(os.environ, XDG_CONFIG_HOME=home)
    environment.pop("ANTHROPIC_API_KEY", None)
    url = subprocess.run([sys.executable, "-m", "claudish", "settings", "--url", "http://127.0.0.1:%d" % port,
                          "--print"], cwd=ROOT, env=environment, capture_output=True, text=True, check=True).stdout.strip()
    config = Path(home) / "claudish" / "config.json"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=args.executable)
        page = await browser.new_page(viewport={"width": 560, "height": 800})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(url)
        assert "#" not in page.url, "the token stays out of the address"
        await expect(page.locator("#status")).to_have_text("cd_AI is running.")  # the rules backend, in words
        await expect(page.locator("input[name=choice][value=claude]")).to_be_checked()
        await expect(page.locator("#key-state")).to_have_text("Not set")
        if args.screenshots:
            await page.screenshot(path=str(args.screenshots / "settings.png"), full_page=True)

        await page.get_by_text("Bard", exact=True).click()  # a tone, at once
        await expect(page.locator("#tone-message")).to_have_text("Bard it is.")
        assert json.loads(config.read_text())["profiles"]["claude"]["tone"] == "bard"
        await page.get_by_text("Described", exact=True).click()
        await page.locator("#own-words").fill("plain and friendly")
        await page.locator("#own-words").press("Enter")
        await page.locator("#own-words").blur()
        await expect(page.locator("#tone-message")).to_have_text("Tone saved.")
        assert json.loads(config.read_text())["profiles"]["claude"]["tone"] == "plain and friendly"

        await page.get_by_text("Another model API").click()  # the form first: nothing switched yet
        await expect(page.locator("#server")).to_be_visible()
        assert json.loads(config.read_text())["profile"] == "claude"
        await page.locator("#url").fill("http://127.0.0.1:%d" % free_port())  # nothing there
        await page.locator("#model").fill("gemma-4")
        await page.locator("#server button").click()
        await expect(page.locator("#model-message")).to_contain_text("Nothing answers at")
        assert json.loads(config.read_text())["profile"] == "claude"  # not switched to a server that is not there
        await page.locator("#url").fill(args.server)
        await page.locator("#server button").click()
        await expect(page.locator("#model-message")).to_have_text("cd_AI now writes with this API.")
        profile = json.loads(config.read_text())["profiles"]["ollama"]
        assert (profile["model_url"], profile["model"]) == (args.server, "gemma-4"), profile
        await expect(page.locator("#status")).not_to_have_class("bad")  # it answers (this service's flag keeps rules)

        await page.set_viewport_size({"width": 360, "height": 700})
        await page.wait_for_function("() => document.documentElement.scrollWidth <= window.innerWidth", timeout=2000)

        bare = await browser.new_page()  # without the token: the page, and nothing in it
        await bare.goto(url.split("#")[0])
        await expect(bare.locator("#status")).to_contain_text("Settings…")
        await page.reload()  # the window keeps its own settings token
        await expect(page.locator("#status")).to_have_text("cd_AI is running.")
        reused = await browser.new_page()  # a ticket is good once
        await reused.goto(url)
        await expect(reused.locator("#status")).to_contain_text("expired")
        assert not errors, errors
        await browser.close()
    print("Settings page passed: ticket kept out of the address and good once, tones (named, described), "
          "a model server (nothing there: not switched; then switched), reload, narrow window, no ticket no settings")


class Models(BaseHTTPRequestHandler):
    """A model server's model list, as Ollama and LM Studio answer it."""

    def do_GET(self):
        body = b'{"data": [{"id": "gemma-4"}]}'
        self.send_response(200 if self.path == "/v1/models" else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--executable")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    models = ThreadingHTTPServer(("127.0.0.1", 0), Models)
    threading.Thread(target=models.serve_forever, daemon=True).start()
    args.server = "http://127.0.0.1:%d" % models.server_port
    with tempfile.TemporaryDirectory() as home:
        port = free_port()
        service = subprocess.Popen([sys.executable, "-m", "claudish", "serve", "--backend", "rules", "--port", str(port)],
                                   cwd=ROOT, env=dict(os.environ, XDG_CONFIG_HOME=home),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                if Path(home, "claudish", "service-token").exists():
                    break
                time.sleep(0.1)
            asyncio.run(check(args, home, port))
        finally:
            service.terminate()
            service.wait(5)


if __name__ == "__main__":
    main()
