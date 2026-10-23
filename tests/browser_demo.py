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

            # The demo opens in compose (the pitch); a Shift tap reaches continue, where the installed
            # input method starts: keys go straight in, and a pause after a word offers the rest.
            await page.locator("#editor").click()
            await expect(page.locator("#source-mode")).to_have_text("compose")
            await keys.press("Shift")
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
            await page.wait_for_timeout(600)  # taking it is not a pause: nothing new is offered
            await expect(page.locator("#ghost")).to_be_empty()
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

            # Compose (a Shift tap): your words are a composition; Tab asks for the rewrite, which takes
            # their place (no list), Esc brings them back, and Tab again keeps the rewrite.
            await keys.press("Shift")
            await expect(page.locator("#source-mode")).to_have_text("compose")
            before = await committed_text()
            await keys.type("This is very important.", delay=20)
            await expect(page.locator("#preedit")).to_have_text("This is very important.")
            await expect(window).to_contain_text("rewrite", timeout=3000)  # after a pause: Tab rewrite, Enter ask
            await keys.press("Tab")  # asks; the rewrite takes your words' place as it arrives
            await expect(window).to_contain_text("Rewrite", timeout=10000)  # it waits in the panel; your words stay
            rewrite = await page.locator("#candidates .k-body").text_content()  # the rewrite, in the panel
            print("Real backend, rewrite:", repr(rewrite))
            assert rewrite != "This is very important.", rewrite
            if args.screenshots:
                await page.screenshot(path=str(args.screenshots / "rewrite.png"))
            await keys.press("Escape")  # your words again
            await expect(page.locator("#preedit")).to_have_text("This is very important.")
            await expect(window).to_contain_text("drop")  # the next Esc drops them: the footer says so
            await keys.press("Tab")
            await keys.press("Tab")  # converted, then kept
            await expect(committed).to_have_attribute("data-text", before + rewrite)
            await keys.type("hello-world", delay=20)  # kept as typed (em dashes come from the model)
            await expect(page.locator("#preedit")).to_have_text("hello-world")
            await keys.press("Shift+Enter")  # keeps your words as they are
            await expect(committed).to_have_attribute("data-text", before + rewrite + "hello-world")
            # Paste in compose joins the composition, to be rewritten like typed words.
            await page.evaluate("() => navigator.clipboard.writeText('a pasted phrase')")
            await keys.press("Control+V")
            await expect(page.locator("#preedit")).to_have_text("a pasted phrase")
            await keys.press("Shift+Enter")  # kept as it is
            await expect(committed).to_have_attribute("data-text", before + rewrite + "hello-world" + "a pasted phrase")
            await page.locator("#copy").click()
            assert await page.evaluate("() => navigator.clipboard.readText()") == await committed_text()
            # A text box: a right click keeps the keyboard; select, copy, and type over a selection.
            await page.locator("#editor").click(button="right")
            await keys.press("Escape")  # close the browser's context menu
            await keys.press("Shift")  # compose -> continue
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
            await keys.press("Shift")  # back to compose
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
            await keys.press("Tab")  # asks (held)
            await asyncio.wait_for(first_started.wait(), timeout=3)
            await keys.type(" now", delay=10)  # typing on: that answer is stale
            release.set()
            await page.wait_for_timeout(300)
            await expect(page.locator("#preedit")).to_have_text("an earlier thought now")  # it never lands
            await keys.press("Tab")
            await expect(window.locator(".k-body")).to_have_text("Rewrite: an earlier thought now")  # in the panel
            assert not any("an earlier thought" in u and "now" not in u for u in await page.evaluate("window.candidateUpdates")
                           if "Rewrite: an earlier thought" in u), "the stale answer showed"
            await page.unroute("**/suggest", controlled)
            await keys.press("Escape")  # your words again
            await keys.press("Shift+Enter")  # and kept
            await page.locator("#clear").click()

            async def unavailable(route):
                await route.fulfill(status=503, content_type="application/json",
                                    body=json.dumps({"error": "model unavailable"}))

            await page.route("**/suggest", unavailable)
            await page.locator("#editor").click()
            await keys.type("Keep this thought intact.", delay=10)
            await keys.press("Tab")  # asks: the service fails
            await expect(page.locator("#preedit")).to_have_text("Keep this thought intact.")
            await expect(window).to_contain_text("the request failed")  # the panel says why; Enter retries
            await keys.press("Escape")  # past the failure: your words, still composing
            await keys.press("Shift+Enter")  # kept
            await expect(committed).to_have_attribute("data-text", "Keep this thought intact.")
            await page.unroute("**/suggest", unavailable)
            await page.locator("#clear").click()

            # Instruct (Enter in compose): held until Enter; ↓ and Tab pick.
            sent = []
            page.on("request", lambda request: sent.append(request.post_data_json)
                    if request.url.endswith("/suggest") else None)
            await expect(page.locator("#source-mode")).to_have_text("compose")
            await keys.type("thank the team for shipping the release", delay=10)
            await page.wait_for_timeout(600)
            assert not any(body and body.get("mode") == "instruct" for body in sent), "sent before Enter"
            await expect(window).to_contain_text("ask", timeout=3000)  # the panel, open at the end of the text
            await keys.press("Enter")
            await expect(window.locator(".k-row").first).to_be_visible(timeout=10000)  # the drafts
            # The text left, so the panel moved back to the caret (it does not stay where the text ended).
            panel_left = (await window.bounding_box())["x"]
            caret_left = (await page.locator("#caret").bounding_box())["x"]
            assert panel_left <= caret_left, ("the panel stayed where the sent text ended", panel_left, caret_left)
            assert any(body and body.get("mode") == "instruct" for body in sent), sent
            # Esc closes the drafts and keeps the instruction to refine; Enter sends it again.
            await keys.press("Escape")
            await expect(page.locator("#preedit")).to_have_text("thank the team for shipping the release")
            await expect(window.locator(".k-row")).to_have_count(0)  # drafts closed
            await expect(window).to_contain_text("ask", timeout=3000)  # after a pause, the keys: Tab rewrite, Enter ask
            await keys.press("Enter")
            await expect(window.locator(".k-row").first).to_be_visible(timeout=10000)  # the drafts
            choices = window.locator(".k-row")
            if await choices.count() > 1:
                if args.screenshots:
                    await page.screenshot(path=str(args.screenshots / "instruct.png"))
                count = await choices.count()
                second = await choices.nth(1).locator(".k-text").text_content()
                await keys.press("Enter")  # Enter talks to the model: it never inserts a draft
                await expect(window.locator(".k-take .k-cap.lit")).to_have_count(1)  # it lights the row's Tab
                assert await committed_text() == "", "Enter inserted a draft"
                await keys.press("ArrowDown")  # choices are not numbered: ↓ then Tab
                await keys.press("Tab")
                await expect(committed).to_have_attribute("data-text", second)
                print("instruct offered %d readings; ↓ Tab inserted the second" % count)
            else:
                draft = await window.locator(".k-row .k-text").first.text_content()
                await keys.press("Tab")  # Tab takes the model's text
                await expect(committed).to_have_attribute("data-text", draft)
            await page.locator("#clear").click()
            await keys.type("never mind", delay=10)  # an instruction you drop: Esc, nothing inserted
            await keys.press("Escape")
            await expect(page.locator("#preedit")).to_have_text("")
            await expect(committed).to_have_attribute("data-text", "")

            # Rewrite a selection: Tab takes it into the composition and rewrites it in place; Esc twice
            # puts the original back where it was.
            await page.locator("#clear").click() if await page.locator("#clear").is_enabled() else None
            await keys.type("plain words", delay=5)
            await keys.press("Shift+Enter")  # kept as typed
            await keys.press("Control+A")
            await keys.press("Tab")
            await expect(window).to_contain_text("Rewrite", timeout=10000)  # it waits in the panel; your words stay
            await expect(committed).to_have_attribute("data-text", "")  # out of the text while it is rewritten
            await keys.press("Escape")
            await keys.press("Escape")
            await expect(committed).to_have_attribute("data-text", "plain words")

            # A sample over a selection replaces it, with no empty line left behind.
            await page.locator("#clear").click() if await page.locator("#clear").is_enabled() else None
            await keys.type("old words", delay=5)
            await keys.press("Shift+Enter")  # kept as typed
            await keys.press("Control+A")
            await page.locator("[data-label=rewrite]").click()  # types, then Tab rewrites it
            await expect(window).to_contain_text("Rewrite", timeout=10000)  # it waits in the panel; your words stay
            await expect(committed).to_have_attribute("data-text", "")  # the selection went; no empty line
            await keys.press("Escape")
            await keys.press("Escape")  # the sample goes too
            await expect(page.locator("#preedit")).to_have_text("")

            # A sample types itself, key by key, in its own mode.
            await page.locator("[data-label=rewrite]").click()
            await expect(page.locator("#source-mode")).to_have_text("compose")
            await expect(window).to_contain_text("Rewrite", timeout=10000)  # typed, then Tab: the rewrite waits in the panel

            await page.set_viewport_size({"width": 390, "height": 844})
            assert await page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
            if args.screenshots:
                await page.screenshot(path=str(args.screenshots / "mobile.png"), full_page=True)
            assert not errors, errors
            print("Browser acceptance passed: continue (ghost, Tab, literal keys), rewrite (waits in the panel, "
                  "Esc back, dash, Tab, Enter), instruct Esc (back, drop), paste as context, clipboard, selection, clear, stale responses, service failure, instruct, samples, "
                  "theme toggle, and mobile layout")
        finally:
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18765")
    parser.add_argument("--executable", help="Optional path to an existing Chromium executable")
    parser.add_argument("--screenshots", type=Path)
    asyncio.run(check(parser.parse_args()))
