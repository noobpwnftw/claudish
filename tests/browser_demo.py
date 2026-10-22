"""Optional browser acceptance test; run against a running Claudish service.

Requires Playwright and Chromium. Does not install or start the model. The demo is an input method,
drawn: keys go to the editor, and the test reads what was committed, the composition, the grey
suggestion, and the candidate window, as a person would see them.
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
        committed = page.locator("#page")
        window = page.locator("#candidates")
        keys = page.keyboard

        async def committed_text():
            return await committed.get_attribute("data-text")

        try:
            await page.goto(args.url)
            await expect(page.locator("#connection")).to_contain_text("connected")
            # One button flips the theme (system first; nothing stored).
            first = await page.evaluate("() => document.documentElement.dataset.theme")
            await page.locator("#theme-toggle").click()
            flipped = await page.evaluate("() => document.documentElement.dataset.theme")
            assert {first, flipped} == {"light", "dark"}, (first, flipped)
            await page.locator("#theme-toggle").click()

            # Continue (where cd_AI starts): keys go straight in; a pause after a word offers the rest.
            await page.locator("#editor").click()
            await expect(page.locator("#source-mode")).to_have_text("continue")
            await keys.type("Thanks for the review ", delay=20)
            await expect(committed).to_have_attribute("data-text", "Thanks for the review ")
            await expect(page.locator("#ghost")).not_to_be_empty(timeout=10000)
            ghost = await page.locator("#ghost").text_content()
            print("Real backend, continue:", repr(ghost), "|", await page.locator("#timing").text_content())
            if args.screenshots:
                args.screenshots.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(args.screenshots / "continue.png"))
            await keys.press("Tab")
            await expect(committed).to_have_attribute("data-text", "Thanks for the review " + ghost)
            await keys.press("Enter")
            await keys.type("ls -la", delay=20)  # literal: the hyphen stays a hyphen
            await expect(committed).to_have_attribute("data-text", "Thanks for the review " + ghost + "\nls -la")
            await keys.press("Enter")
            # A paste goes in like typing, and is the next suggestion's context.
            continued = []
            page.on("request", lambda request: continued.append(request.post_data_json.get("text"))
                    if request.url.endswith("/suggest") and request.post_data_json else None)
            await page.evaluate("() => navigator.clipboard.writeText('The release is ready. ')")
            await keys.press("Control+v")
            await keys.type("We ship ", delay=20)
            await expect(page.locator("#ghost")).not_to_be_empty(timeout=10000)
            assert any(t and t.endswith("The release is ready. We ship ") for t in continued), continued
            await keys.press("Escape")  # dismiss it
            await keys.press("Enter")

            # Rewrite (F7 twice): your words are a composition; the candidate window is under it.
            await keys.press("F7")
            await keys.press("F7")
            await expect(page.locator("#source-mode")).to_have_text("rewrite")
            before = await committed_text()
            await keys.type("This is very important.", delay=20)
            await expect(page.locator("#preedit")).to_have_text("This is very important.")
            await expect(window).to_be_visible(timeout=10000)
            rewrite = (await window.locator(".candidate-row").first.text_content()).removeprefix("Tab")
            print("Real backend, rewrite:", repr(rewrite))
            if args.screenshots:
                await page.screenshot(path=str(args.screenshots / "rewrite.png"))
            await keys.press("Tab")
            await expect(committed).to_have_attribute("data-text", before + rewrite)
            await keys.type("hello-world", delay=20)  # in rewrite, the dash is Claudish
            await expect(page.locator("#preedit")).to_have_text("hello—world")
            await keys.press("Enter")  # keeps your words
            await expect(committed).to_have_attribute("data-text", before + rewrite + "hello—world")
            await page.locator("#copy").click()
            assert await page.evaluate("() => navigator.clipboard.readText()") == await committed_text()
            # A text box: a right click keeps the keyboard; select, copy, and type over a selection.
            await page.locator("#editor").click(button="right")
            await keys.press("Escape")  # close the browser's context menu
            await keys.press("F7")  # rewrite -> continue
            await keys.press("End")
            await keys.type("!", delay=10)
            text = await committed_text()
            assert text.endswith("!"), text
            await keys.press("Control+a")
            await keys.press("Control+c")
            assert await page.evaluate("() => navigator.clipboard.readText()") == text
            await keys.type("Replaced", delay=10)
            await expect(committed).to_have_attribute("data-text", "Replaced")
            await keys.press("Shift+Home")
            await keys.press("Delete")
            await expect(committed).to_have_attribute("data-text", "")
            await keys.press("F7")
            await keys.press("F7")  # back to rewrite
            await expect(page.locator("#clear")).to_be_disabled()  # nothing left to clear

            # A stale answer must never appear: hold the first request, type on, then release it.
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
                  document.getElementById('candidates').textContent)).observe(
                  document.getElementById('candidates'), {childList: true, subtree: true});
            }""")
            await page.locator("#editor").click()
            await keys.type("an earlier thought", delay=10)
            await asyncio.wait_for(first_started.wait(), timeout=3)
            await keys.type(" now", delay=10)
            release.set()
            await expect(window).to_contain_text("Rewrite: an earlier thought now")
            assert not any("Rewrite: an earlier thought" in u and "now" not in u
                           for u in await page.evaluate("() => window.candidateUpdates"))
            await page.unroute("**/suggest", controlled)
            await keys.press("Escape")
            await page.locator("#clear").click()

            async def unavailable(route):
                await route.fulfill(status=503, content_type="application/json",
                                    body=json.dumps({"error": "model unavailable"}))

            await page.route("**/suggest", unavailable)
            await page.locator("#editor").click()
            await keys.type("Keep this thought intact.", delay=10)
            await expect(page.locator("#status")).to_contain_text("model unavailable")
            await expect(page.locator("#preedit")).to_have_text("Keep this thought intact.")
            await keys.press("Escape")  # keeps your words
            await expect(committed).to_have_attribute("data-text", "Keep this thought intact.")
            await page.unroute("**/suggest", unavailable)
            await page.locator("#clear").click()

            # Instruct (rewrite -> continue -> instruct): held until Enter; a digit picks.
            sent = []
            page.on("request", lambda request: sent.append(request.post_data_json)
                    if request.url.endswith("/suggest") else None)
            await keys.press("F7")
            await keys.press("F7")
            await expect(page.locator("#source-mode")).to_have_text("instruct")
            await keys.type("thank the team for shipping the release", delay=10)
            await page.wait_for_timeout(600)
            assert not any(body and body.get("mode") == "instruct" for body in sent), "sent before Enter"
            await keys.press("Enter")
            await expect(window.locator(".candidate-row").first).not_to_have_text("working…", timeout=10000)
            assert any(body and body.get("mode") == "instruct" for body in sent), sent
            choices = window.locator("button.candidate-row")
            if await choices.count() > 1:
                if args.screenshots:
                    await page.screenshot(path=str(args.screenshots / "instruct.png"))
                count = await choices.count()
                second = (await choices.nth(1).text_content())[1:]
                await keys.press("2")
                await expect(committed).to_have_attribute("data-text", second)
                print("instruct offered %d readings; 2 inserted the second" % count)
            else:
                draft = (await window.locator(".candidate-row").first.text_content()).removeprefix("Enter")
                await keys.press("Enter")
                await expect(committed).to_have_attribute("data-text", draft)
            await page.locator("#clear").click()

            # A sample types itself, key by key, in its own mode.
            await page.locator("[data-mode=rewrite]").click()
            await expect(page.locator("#source-mode")).to_have_text("rewrite")
            await expect(page.locator("#preedit")).to_have_text("This is very important.", timeout=5000)
            await expect(window).to_be_visible(timeout=10000)

            await page.set_viewport_size({"width": 390, "height": 844})
            assert await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
            if args.screenshots:
                await page.screenshot(path=str(args.screenshots / "mobile.png"), full_page=True)
            assert not errors, errors
            print("Browser acceptance passed: continue (ghost, Tab, literal keys), rewrite (candidate window, "
                  "dash, Tab, Enter), paste as context, clipboard, selection, clear, stale responses, service failure, instruct, samples, "
                  "theme toggle, and mobile layout")
        finally:
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18765")
    parser.add_argument("--executable", help="Optional path to an existing Chromium executable")
    parser.add_argument("--screenshots", type=Path)
    asyncio.run(check(parser.parse_args()))
