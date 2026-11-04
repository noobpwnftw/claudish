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


def typed():
    """How the page names claudish's commands: as the service, this interpreter, runs them."""
    return subprocess.run([sys.executable, "-c", "from claudish.service import typed; print(typed())"],
                          capture_output=True, text=True, check=True).stdout.strip()


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
        expect.set_options(timeout=1000)
        page = await browser.new_page(viewport={"width": 560, "height": 800})
        page.set_default_timeout(1000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        authenticated = asyncio.Event()

        async def delayed_session(route):
            await authenticated.wait()
            await route.continue_()

        await page.route("**/settings/session", delayed_session)
        await page.goto(url)
        # A packaged app's cold start can leave the page visible before its session is ready.
        # A fast first click must wait, rather than posting a setting without its token.
        await expect(page.locator("#controls")).to_be_hidden()
        await expect(page.locator("input[name=choice][value=claude-code]")).to_be_disabled()
        authenticated.set()
        assert "#" not in page.url, "the token stays out of the address"
        await expect(page.locator("#status")).to_have_text("cd_AI is running.")  # the rules backend, in words
        await expect(page.locator("input[name=choice][value=claude]")).to_be_checked()
        for name in ("Claude Code", "Codex"):  # subscriptions, through their commands (not clicked here)
            await expect(page.get_by_text(name, exact=True)).to_be_visible()
        await expect(page.locator("#key-state")).to_have_text("Not set")
        await expect(page.get_by_text("A Claude subscription, through the claude command.", exact=False)).to_be_visible()
        if args.screenshots:
            await page.screenshot(path=str(args.screenshots / "settings.png"), full_page=True)

        await page.get_by_text("Bard", exact=True).click()  # a tone, at once
        await expect(page.locator("#tone-message")).to_have_text("Bard it is.")
        assert json.loads(config.read_text())["tone"] == "bard"
        await page.get_by_text("Described", exact=True).click()
        await page.locator("#own-words").fill("plain and friendly")
        await page.locator("#own-words").press("Enter")
        await page.locator("#own-words").blur()
        await expect(page.locator("#tone-message")).to_have_text("Tone saved.")
        assert json.loads(config.read_text())["tone"] == "plain and friendly"

        await expect(page.locator("input[name=hints][value=on]")).to_be_checked()
        await page.get_by_text("Only what is pending", exact=True).click()
        await expect(page.locator("#hints-message")).to_have_text("The panel shows only what is pending.")
        assert json.loads(config.read_text())["hints"] is False

        await page.get_by_text("Another model API").click()  # the form first: nothing switched yet
        await expect(page.locator("#server")).to_be_visible()
        await expect(page.locator("#try")).to_be_hidden()  # it would try the model still in use
        assert json.loads(config.read_text())["profile"] == "claude"
        await page.locator("#url").fill("http://127.0.0.1:%d" % free_port())  # nothing there
        await page.locator("#model").fill("gemma-4")
        await page.locator("#server button").click()
        await expect(page.locator("#model-message")).to_contain_text("Nothing answers at")
        assert json.loads(config.read_text())["profile"] == "claude"  # not switched to a server that is not there
        await expect(page.locator("#try")).to_be_hidden()
        await page.locator("#url").fill(args.server)
        await page.locator("#server button").click()
        await expect(page.locator("#model-message")).to_have_text("cd_AI now writes with this API.")
        await expect(page.locator("#try")).to_be_visible()
        profile = json.loads(config.read_text())["profiles"]["server"]
        assert (profile["model_url"], profile["model"]) == (args.server, "gemma-4"), profile
        await expect(page.locator("#status")).not_to_have_class("bad")  # it answers (this service's flag keeps rules)

        await page.set_viewport_size({"width": 360, "height": 700})
        await page.wait_for_function("() => document.documentElement.scrollWidth <= window.innerWidth", timeout=2000)

        bare = await browser.new_page()  # without the token: the page, and nothing in it
        await bare.goto(url.split("#")[0])
        await expect(bare.locator("#status")).to_contain_text("Settings…")
        await expect(bare.locator("#controls")).to_be_hidden()
        await page.reload()  # the window keeps its own settings token
        await expect(page.locator("#status")).to_have_text("cd_AI is running.")

        # The native subscription backends report their own names and lifecycle state. Exercise
        # the page's real fetch/render path; no CLI login or model is needed for these UI states.
        lifecycle = {"backend": "claude-code", "model": "warm"}

        async def subscription_state(route):
            if route.request.url.endswith("/settings") and route.request.method != "POST":
                await route.continue_()
                return
            response = await route.fetch()
            data = await response.json()
            data.update(choice=lifecycle["backend"], service=dict(lifecycle), command="/opt/codex/bin/codex")
            await route.fulfill(response=response, json=data)

        async def health(route):
            await route.fulfill(json={"backend": lifecycle["backend"], "model": "warm"})

        async def rewrite(route):
            body = route.request.post_data_json
            await route.fulfill(json={"text": "A rewrite of " + body["text"]})

        await page.route("**/settings/state", subscription_state)
        await page.route("**/settings", subscription_state)
        await page.route("**/health", health)
        await page.route("**/suggest", rewrite)
        for backend, name in (("claude-code", "Claude Code"), ("codex", "Codex")):
            lifecycle.update(backend=backend, model="warm")
            await page.reload()
            await expect(page.locator("#status")).to_have_text(f"Ready: {name} writes for you.")
            await page.locator("#try-text").fill("hello")
            await page.locator("#try button").click()
            await expect(page.locator("#sample")).to_have_text("“hello” → “A rewrite of hello”")
        lifecycle["model"] = "failed: Codex: login required"
        await page.reload()
        await expect(page.locator("#status")).to_have_text(
            "Codex could not start: login required. Run /opt/codex/bin/codex in a terminal and log in, then try a rewrite.")
        await expect(page.locator("#try button")).to_be_enabled()  # retry after logging in
        await page.locator("#try button").click()
        await expect(page.locator("#status")).to_have_text("Ready: Codex writes for you.")
        lifecycle["model"] = "starting"
        await page.reload()
        await expect(page.locator("#status")).to_have_text("Starting Codex…")
        await expect(page.locator("#status")).to_have_text("Ready: Codex writes for you.")
        # Its model cannot run here (no Anthropic SDK): said, and another model can still be picked.
        lifecycle.update(backend="none", unavailable="the claude backend needs the Anthropic SDK: pip install it.")
        await page.reload()
        await expect(page.locator("#status")).to_have_text(
            "cd_AI has no model: the claude backend needs the Anthropic SDK: pip install it.")
        await expect(page.locator("#controls")).to_be_visible()
        del lifecycle["unavailable"]
        lifecycle.update(backend="codex", model="warm")
        # Claude picked but the service cannot switch to it: the radio goes back to what is in use.

        async def refused(route):
            if route.request.method == "POST" and (route.request.post_data_json or {}).get("choice") == "claude":
                await route.fulfill(status=400, json={"error": "could not use that, so nothing changed"})
            else:
                await subscription_state(route)
        await page.route("**/settings", refused)
        await page.reload()
        await expect(page.locator("#status")).to_have_text("Ready: Codex writes for you.")
        await page.locator("input[name=choice][value=claude]").check()
        await expect(page.locator("#model-message")).to_contain_text("nothing changed")
        await expect(page.locator("input[name=choice][value=codex]")).to_be_checked()
        await page.unroute("**/settings", refused)

        # A late response from the previous model must not overwrite a newer example.
        pending, release = asyncio.Event(), asyncio.Event()

        async def delayed_rewrite(route):
            text = route.request.post_data_json["text"]
            if text == "old":
                pending.set()
                await release.wait()
            await route.fulfill(json={"text": "A rewrite of " + text})

        await page.route("**/suggest", delayed_rewrite)
        await page.locator("#try-text").fill("old")
        await page.locator("#try button").click()
        await asyncio.wait_for(pending.wait(), 1)
        # render invalidates the old example when settings change; use the real tone save.
        await page.locator("#try-text").fill("new")
        await page.get_by_text("Bard", exact=True).click()
        await expect(page.locator("#tone-message")).to_have_text("Bard it is.")
        release.set()
        await expect(page.locator("#sample")).not_to_contain_text("A rewrite of old")
        await page.locator("#try button").click()
        await expect(page.locator("#sample")).to_have_text("“new” → “A rewrite of new”")

        # A config the service does not use, or a profile the window switches to: said, with the fix.
        await page.unroute_all()
        problem = "profile 'claude': unknown keys claude_model"
        fix = "Fix it in %s (it applies when you save), or move that file aside and run %s init." % (config, typed())

        async def refused(route):
            response = await route.fetch()
            data = await response.json()
            data["service"].update(backend="none", problem=problem)
            await route.fulfill(response=response, json=data)

        async def stale(route):  # the service is fine; a profile the window switches to is not
            response = await route.fetch()
            data = await response.json()
            data["config_problem"] = problem
            await route.fulfill(response=response, json=data)

        await page.route("**/settings/state", stale)
        await page.reload()
        await expect(page.locator("#status")).to_have_text("cd_AI is running.")
        await expect(page.locator("#config-fix")).to_have_text("A model you can pick here does not read: %s. %s" % (problem, fix))
        await expect(page.locator("#controls")).to_be_visible()  # only picking that model fails
        await page.unroute_all()
        await page.route("**/settings/state", refused)
        await page.reload()
        await expect(page.locator("#status")).to_have_text("cd_AI does not use its config: %s." % problem)
        await expect(page.locator("#config-fix")).to_have_text(fix)
        await expect(page.locator("#controls")).to_be_hidden()  # every change would be refused: only the problem
        if args.screenshots:
            await page.screenshot(path=str(args.screenshots / "settings-config-problem.png"), full_page=True)
        await page.unroute_all()  # the file fixed: the window notices without a reload
        await expect(page.locator("#config-fix")).to_be_hidden(timeout=4000)
        await page.route("**/settings", lambda route: route.abort())  # the service gone: the same
        await page.get_by_text("Critic", exact=True).click()
        await expect(page.locator("#status")).to_contain_text("cd_AI's service is not running.")
        await expect(page.locator("#controls")).to_be_hidden()
        await page.unroute_all()
        await expect(page.locator("#config-fix")).to_be_hidden(timeout=4000)
        await expect(page.locator("#controls")).to_be_visible()
        # The service restarted: this window's token is gone. Reopen, not "not running" forever.
        await page.route("**/settings", lambda route: route.fulfill(status=403, json={"error": "the service token is required"}))
        await page.get_by_text("Critic", exact=True).click()  # not the tone in use: a change
        await expect(page.locator("#status")).to_contain_text("This window has expired: open Settings again")
        await expect(page.locator("#controls")).to_be_hidden()
        await page.unroute_all()

        reused = await browser.new_page()  # a ticket is good once
        await reused.goto(url)
        await expect(reused.locator("#status")).to_contain_text("expired")
        assert not errors, errors
        await browser.close()
    print("Settings page passed: ticket kept out of the address and good once, tones (named, described), "
          "a model server (nothing there: not switched; then switched), subscription startup/failure/retry, "
          "first rewrite, stale example ignored, reload, narrow window, no ticket no settings, a config not used: what to fix")


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
                if Path(home, "claudish", "service-token-%d" % port).exists():  # its port's token
                    break
                time.sleep(0.1)
            asyncio.run(check(args, home, port))
        finally:
            service.terminate()
            service.wait(5)


if __name__ == "__main__":
    main()
