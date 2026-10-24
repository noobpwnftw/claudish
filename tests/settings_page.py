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
import time
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
        await expect(page.locator("#status")).to_contain_text("rules")
        await expect(page.locator("input[name=choice][value=claude]")).to_be_checked()
        await expect(page.locator("#key-state")).to_have_text("Not set")
        if args.screenshots:
            await page.screenshot(path=str(args.screenshots / "settings.png"), full_page=True)

        await page.get_by_text("Bard", exact=True).click()  # a voice, at once
        await expect(page.locator("#voice-message")).to_have_text("Bard it is.")
        assert json.loads(config.read_text())["profiles"]["claude"]["tone"] == "bard"
        await page.get_by_text("Your own words", exact=True).click()
        await page.locator("#own-words").fill("plain and friendly")
        await page.locator("#own-words").press("Enter")
        await page.locator("#own-words").blur()
        await expect(page.locator("#voice-message")).to_have_text("Voice saved.")
        assert json.loads(config.read_text())["profiles"]["claude"]["tone"] == "plain and friendly"

        await page.get_by_text("A model server on this computer").click()
        await expect(page.locator("#server")).to_be_visible()
        assert json.loads(config.read_text())["profile"] == "ollama"
        await page.locator("#url").fill("localhost:1234")
        await page.locator("#server button").click()
        await expect(page.locator("#model-message")).to_have_class("message bad")  # said why, nothing written
        await page.locator("#url").fill("http://127.0.0.1:1234")
        await page.locator("#model").fill("gemma-4")
        await page.locator("#server button").click()
        await expect(page.locator("#model-message")).to_have_text("Saved.")
        profile = json.loads(config.read_text())["profiles"]["ollama"]
        assert (profile["model_url"], profile["model"]) == ("http://127.0.0.1:1234", "gemma-4"), profile

        await page.set_viewport_size({"width": 360, "height": 700})
        await page.wait_for_function("() => document.documentElement.scrollWidth <= window.innerWidth", timeout=2000)

        bare = await browser.new_page()  # without the token: the page, and nothing in it
        await bare.goto(url.split("#")[0])
        await expect(bare.locator("#status")).to_contain_text("Settings…")
        assert not errors, errors
        await browser.close()
    print("Settings page passed: token kept out of the address, voices (named, own words), a model "
          "server (refused, then saved), narrow window, no token no settings")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--executable")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
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
