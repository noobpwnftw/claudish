# Use

Typing in detail, the browser demos, and `claudish fix`.

## Typing

| Key/action | Result |
| --- | --- |
| Type | Accumulate the phrase in an editable composition buffer |
| `-` | Insert `—` immediately |
| Pause for 180 ms | Continue only: ask for the rest of the sentence. Rewrite asks on Tab and instruct on Enter, so nothing is sent while you type in those modes |
| F6 | Preview a completed candidate; useful on Windows |
| F7 | Switch mode: continue → instruct → rewrite (Linux shows it in the auxiliary text, Windows in a notice). F7 belongs to the input method while cd_AI is the active input source, so apps do not receive it then |
| Continue mode | Typing goes straight into the app (the model sees it as context); after a pause the rest of the sentence appears after the caret: greyed on Linux, as grey marked text on macOS (apps that draw marked text themselves may show it underlined), and in the candidate window on Windows (F6 shows it). Tab takes it, Esc dismisses it, and typing ignores it. Tab, Enter, Backspace, and arrows are the app's when nothing is offered. A focus change only ever drops the suggestion: IBus discards commits made during focus-out, so a suggestion inside the composition would either lose your words or commit text you never accepted |
| Enter (instruct) | Send the held instruction; Enter again (or Tab) inserts the result |
| Esc (instruct) | One step back: with drafts showing (or an answer pending), close them and keep the instruction to refine and send again, as a follow-up in the same conversation; with just the instruction, drop it (nothing is inserted) |
| 1–9 (instruct list) | An instruction offers up to three readings as a numbered list, as in a CJK input method; a digit inserts that one, Enter or Tab the first. While you type, digits are text. A profile sets the count per mode: `"modes": {"instruct": {"candidates": 1}}` |
| Typing while an agent asks | Composes a reply instead of a number; Enter sends it (the agent hears it as your reason), Backspace edits it, Esc clears it, and digits in it are text |
| F8 (instruct) | Also send a picture of the focused window with this instruction (see [Window pictures](configuration.md#window-pictures)) |
| Tab (rewrite) | Ask for the rewrite; it takes your words' place as it arrives, as a CJK input method converts what you typed ("rewriting…" while it comes). Tab again (or Enter, or typing on) keeps it; Esc or Backspace brings your words back. Rewrite has no list |
| Tab with a selection (rewrite) | With nothing composed, rewrite the selected text in place (CJK input methods call this reconversion): it leaves the text while it is rewritten, Tab keeps the rewrite, Esc twice puts your words back. macOS and the demo; on Linux only where the toolkit reports selections (GTK3 and GTK4 do not, in our tests) |
| Enter / Escape (rewrite) | Commit your wording, including the em-dash substitution |
| Backspace | Edit the composition and invalidate its candidate |

Enter commits composition first; press it again to send a newline. This first
version edits composition at its end. Linux commits original wording before
forwarding navigation and shortcuts. On Windows, the first navigation key
commits composition and is consumed; press again to navigate. Ctrl/Alt/Win
shortcuts pressed while composing commit your wording and are consumed; press the shortcut again to run it, as with navigation keys. Characters typed with AltGr
(Ctrl+Alt) stay in the composition, as they do on Linux. Application-driven focus
changes and composition termination need particular attention in Windows testing.

Linux refreshes the candidate automatically. PIME's Python protocol delivers
updates in response to host events, so Windows needs F6 to preview after a pause;
Tab can also collect and accept a ready result directly. Number-key candidate
selection is not implemented; use Tab. Short phrases work best: the buffer is
limited to 512 characters and generation to 64 tokens. A truncated or failed
rewrite is never offered; Enter/Escape still commits your wording.

## Browser demo

With the launcher running, open **http://127.0.0.1:18765**. The demo is the
input method, drawn in the page: one editor with an input-source badge, the
composition at the caret, and a candidate window, following the same rules as the
desktop adapters. It opens in rewrite, the pitch (Tab takes the rewrite, Enter
keeps your words); F7 or the badge switches to continue (keys go straight in;
pause after a word and the rest waits in grey; Tab takes it) and instruct (Enter
sends; pick a draft with 1–3). The installed input method starts in continue. A key strip lights the keys as you use them, and each sample
types itself in its own mode. No input method installation is needed. The theme
toggle follows the system by default; a choice lasts only for the current page,
with no cookies or storage.

The page calls the same local model as the desktop adapters. Nothing is saved
in browser storage. If your browser runs on a different machine from the Spark,
forward TCP port **18765** using the VS Code Ports tab or SSH, then open the
forwarded localhost URL. Keep the local port at 18765. Browser requests must
come from the demo's own origin; cross-origin requests remain blocked.

For a model-free UI demo: `python -m claudish serve --backend rules`, then open
the same URL. The page labels this as rules mode.

From a second terminal:

```sh
python -m claudish rewrite "This is very important."
python -m claudish bench --runs 12
```

Example output from the default model:

```text
This is of utmost significance.
```

To run against an existing llama-server instead of starting one:

```sh
python -m claudish serve --model-url http://127.0.0.1:18766
```

## Static demo: the model in your browser

It runs at [claudish.io/demo](https://claudish.io/demo/), under the [project home page](https://claudish.io) (`site/`: what Claudish is, the keys, and an install prompt to paste into a coding agent). `.github/workflows/pages.yml` deploys both on every push to `main` (`python scripts/build_static_demo.py --site`). `python scripts/build_static_demo.py` alone writes `dist/demo/`, the same browser demo
with the model running in the page through [wllama](https://github.com/ngxson/wllama)
(llama.cpp compiled to WebAssembly). It needs no inference server, so any static
host can serve it. Nothing is downloaded until the visitor clicks **Run the model
in this browser**; the 491 MB model (pinned Qwen2.5 0.5B) is then cached by the
browser, and nothing typed leaves the page. A small service worker (`coi-sw.js`)
supplies the cross-origin isolation headers static hosts cannot set, so the
multi-threaded build runs: on the Spark's CPU in headless Chromium, a rewrite
takes about 1 s (9 s single-threaded). Browsers with WebGPU are faster still.
A purpose-trained model of about 150 MB is planned (ROADMAP G21).

## Fix the last failed command

A better [thefuck](https://github.com/nvbn/thefuck): `claudish fix` asks your
configured model to correct the last failed shell command. Add the hook to your
shell's rc file:

```sh
eval "$(claudish shell-hook bash)"    # or zsh; from a checkout: python -m claudish shell-hook bash
gti log --oneline                     # bash: gti: command not found
fix                                   # bash: an editable "fix> git log --oneline"; zsh: placed in your prompt
```

The hook records only failed commands (never Ctrl+C), with their exit status, to
a private file (mode 600) in `$XDG_RUNTIME_DIR`. Unlike thefuck, nothing is ever
re-run to capture output. The model sees the command, its exit status, and, for
an unknown program, the closest installed names by typo distance. The working
directory is not sent. Nothing runs until you press Enter. `claudish fix -- git
psuh` fixes a given command. The model comes from your default profile or
`--profile`.

On [`benchmarks/eval/fix_cases.json`](../benchmarks/eval/fix_cases.json), 30
cases on the Spark: 23 need a fix, and 7 are legitimate commands that failed
for environmental reasons, which must be left alone.

| Model / Q4_K_M | Fixed | Wrong | No fix | Left alone | Harmful | Median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen2.5 0.5B Instruct | 15 / 23 | 3 | 5 | 6 / 7 | 1 | 38 ms |
| Qwen2.5 1.5B Instruct | 22 / 23 | 0 | 1 | 7 / 7 | 0 | 54 ms |

Reproduce with `python benchmarks/evaluate_fix.py --label NAME` against a model
server. The bash hook is tested; the zsh hook has not been run yet.

## Talking to a coding agent in its own chat box

A worked example of the scope (one turn at the caret, nothing more): typing to
Claude Code in VS Code.

- **Continue** completes your message as you type, from the text already in the
  chat box. On macOS, VS Code and other Chromium apps share only about 100
  characters around the caret with an input method, which is plenty for a
  message.
- **Instruct** turns a one-line task into the message: "tell it to add a test for
  the retry" becomes a full request, drafted at the caret for you to send.
- **The code you are looking at** comes from F8 (a picture of the window, for a
  vision model) or from MCP servers you configure for Claudish; Claudish does not
  read Claude Code's own configuration or connection.
- **Permissions**: if a tool you configured needs one (fetching a site, say), it
  asks in the candidate list: 1 allow, 2 deny.

It is not a replacement for the extension: the conversation with the agent stays
in the agent's own window.

## What cd_AI tells the model about the text box

Every request carries what the input method knows about where you are typing,
described the same way for every mode:

- **the app** (the program, or the bundle on macOS), which also picks the
  profile's bindings;
- **the field's kind** when the app reports it (IBus: terminal, email, URL,
  number, and so on). URL, email, number, and phone fields get no unasked
  suggestions; Tab and Enter still work there;
- **the text around the caret**: for continue, the text before it (the
  suggestion's start) and after it; for rewrite, where your phrase goes; for
  instruct, a window of the text box, with the rest available as retrieval.

Windows (PIME) reports only the app so far; macOS reports no field kind.

