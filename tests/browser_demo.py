"""Optional browser acceptance test; run against a running Claudish service.

Requires Playwright and Chromium. Does not install or start the model.
"""
import argparse
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, expect


async def check(args):
    async with async_playwright() as playwright:
        options = {"headless": True}
        if args.executable:
            options["executable_path"] = args.executable
        browser = await playwright.chromium.launch(**options)
        context = await browser.new_context(viewport={"width": 1440, "height": 1100},
                                            permissions=["clipboard-read", "clipboard-write"])
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            await page.goto(args.url)
            await expect(page.locator("#connection")).to_contain_text("connected")
            await page.get_by_role("button", name="This is very important.").click()
            await expect(page.locator("#accept")).to_be_enabled(timeout=10000)
            suggestion = await page.locator("#candidate").inner_text()
            assert suggestion.strip()
            print("Real backend:", suggestion, "|", await page.locator("#timing").inner_text())
            if args.screenshots:
                args.screenshots.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(args.screenshots / "desktop.png"), full_page=True)
            await page.locator("#draft").press("Tab")
            await expect(page.locator("#output")).to_have_value(suggestion)
            await expect(page.locator("#draft")).to_have_value("")
            await page.locator("#draft").press_sequentially("hello-world")
            await expect(page.locator("#draft")).to_have_value("hello—world")
            await page.locator("#draft").press("Enter")
            await expect(page.locator("#output")).to_have_value(suggestion + "\n\nhello—world")
            await page.locator("#dash-toggle").uncheck()
            await page.locator("#draft").press_sequentially("a-b")
            await expect(page.locator("#draft")).to_have_value("a-b")
            await page.locator("#draft").press("Escape")
            await page.locator("#copy").click()
            assert await page.evaluate("() => navigator.clipboard.readText()") == await page.locator("#output").input_value()
            await page.locator("#clear").click()
            await expect(page.locator("#output")).to_have_value("")

            # Deliver an old result after the draft changes; it must never appear.
            first_started, release = asyncio.Event(), asyncio.Event()

            async def controlled(route):
                text = route.request.post_data_json["text"]
                if text == "an earlier thought":
                    first_started.set()
                    await release.wait()
                await route.fulfill(status=200, content_type="application/json", body=json.dumps(
                    {"text": "Rewrite: " + text, "backend": "llama", "elapsed_ms": 42}))

            await page.route("**/suggest", controlled)
            await page.evaluate("""() => {
                window.candidateUpdates = [];
                new MutationObserver(() => window.candidateUpdates.push(
                  document.getElementById('candidate').textContent)).observe(
                  document.getElementById('candidate'), {childList: true, subtree: true});
            }""")
            await page.locator("#draft").fill("an earlier thought")
            await asyncio.wait_for(first_started.wait(), timeout=3)
            await page.locator("#draft").fill("a newer thought")
            release.set()
            await expect(page.locator("#candidate")).to_have_text("Rewrite: a newer thought")
            updates = await page.evaluate("() => window.candidateUpdates")
            assert "Rewrite: an earlier thought" not in updates
            await page.unroute("**/suggest", controlled)

            async def unavailable(route):
                await route.fulfill(status=503, content_type="application/json",
                                    body=json.dumps({"error": "model unavailable"}))

            await page.route("**/suggest", unavailable)
            await page.locator("#draft").fill("Keep this thought intact.")
            await expect(page.locator("#feedback")).to_contain_text("model unavailable")
            await expect(page.locator("#draft")).to_have_value("Keep this thought intact.")
            await expect(page.locator("#accept")).to_be_disabled()
            await page.locator("#keep").click()
            await expect(page.locator("#output")).to_have_value("Keep this thought intact.")
            await page.unroute("**/suggest", unavailable)

            # Instruct mode: the typed text is an instruction; the candidate is the draft.
            sent = []
            page.on("request", lambda request: sent.append(request.post_data_json)
                    if request.url.endswith("/suggest") else None)
            await page.locator("#clear").click()
            await page.get_by_role("radio", name="INSTRUCT").check()
            await expect(page.locator("#candidate-title")).to_have_text("THE DRAFT")
            await expect(page.locator("#accept-label")).to_have_text("Accept draft")
            await expect(page.locator("#samples-label")).to_have_text("TRY AN INSTRUCTION")
            await expect(page.get_by_role("button", name="write a two-line story about a cat ↗")).to_be_visible()
            await page.locator("#draft").fill("thank the team for shipping the release")
            await page.wait_for_timeout(600)
            assert not any(body and body.get("mode") == "instruct" for body in sent), "sent before Enter"
            await page.locator("#draft").press("Enter")  # Enter sends the instruction.
            await expect(page.locator("#accept")).to_be_enabled(timeout=10000)
            draft_text = await page.locator("#candidate").inner_text()
            assert draft_text.strip() and any(body and body.get("mode") == "instruct" for body in sent), sent
            await page.locator("#draft").press("Enter")  # The second Enter inserts it.
            await expect(page.locator("#output")).to_have_value(draft_text)
            await page.get_by_role("radio", name="REWRITE").check()
            await expect(page.locator("#candidate-title")).to_have_text("THE CLAUDISH EDIT")
            await page.locator("#clear").click()

            await page.set_viewport_size({"width": 390, "height": 844})
            await page.get_by_role("button", name="Let's explore the options.").click()
            await expect(page.locator("#accept")).to_be_enabled(timeout=10000)
            assert await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
            if args.screenshots:
                await page.screenshot(path=str(args.screenshots / "mobile.png"), full_page=True)
            assert not errors, errors
            print("Browser acceptance passed: inference, Tab/Enter/Escape, dashes, clipboard, "
                  "clear, stale responses, service failure, instruct mode, and mobile layout")
        finally:
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18765")
    parser.add_argument("--executable", help="Optional path to an existing Chromium executable")
    parser.add_argument("--screenshots", type=Path)
    asyncio.run(check(parser.parse_args()))
