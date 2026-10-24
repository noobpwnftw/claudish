# Use

Typing in detail, the browser demos, and terminals.

## Typing

| Key/action | Result |
| --- | --- |
| Type | Continue: straight into the app. Compose: your words gather as the composition (underlined) |
| Pause after a word | Continue only: ask for the rest of the sentence. In compose a rewrite is asked for with Tab and an instruction with Enter |
| Shift (tap) | Switch mode: continue ↔ compose, as Shift switches English and pinyin. A tap is Shift alone, released within half a second, after a pause: Shift with another key (a capital, Shift+Enter), held (Shift+click), or pressed right after another key (rolled typing) is not one. Leaving compose keeps your words as typed. A brief pill at the caret says the mode and where Shift goes next; GNOME's top bar, Windows' taskbar, and the macOS menu bar show it all along |
| Continue mode | Typing goes straight into the app (the model sees it as context); at the end of a line, the rest of the sentence appears after the caret in grey. Tab takes it, Esc dismisses it, typing ignores it. Tab, Enter, Backspace, and arrows are the app's when nothing is offered |
| Starting a composition (compose) | Only a letter or a digit starts one: a space or punctuation typed with nothing composed goes straight into the app. While composing, Space is text |
| Compose keys | The panel at the caret says them from the first key: Tab rewrite · Enter ask · Shift+Enter keep |
| Tab (compose) | Tab takes the model's text. With your words: ask for a rewrite; it shows in the panel ("Rewrite") while your words stay in your text; Tab again puts it in; Esc or typing on keeps your words. With drafts: insert the highlighted one. With an answer to read: insert it (Esc dismisses it). |
| Enter (compose) | Send what you composed as an instruction. It stays underlined at the caret while the model works (a reply you type takes its place); the panel shows what is happening, then the drafts (the first highlighted); Tab inserts the highlighted one. Enter on a draft lights its Tab. With nothing composed, Enter is the app's (a newline) |
| ↑ ↓ | Move the highlight through the drafts (Tab inserts it) or a question's choices (Enter answers with it), no wrap. Choices are not numbered: digits are text, as Space is. An approval starts with nothing highlighted; the first ↓ lands on its safe choice (Deny), and Enter does nothing until a choice is highlighted |
| Typing after you send | What you type goes in at the caret, as a composition: a reply when the model asks (Enter sends it; in an approval, "deny with reason"), or your next words while it works or its drafts show (Enter sends them as a follow-up in the same conversation). The choices fade while you type |
| Shift+Enter (compose) | Keep what you composed as it is, and stay in compose. Most CJK input methods keep the typed letters with Enter; in cd_AI, Enter asks the model and Shift+Enter keeps |
| Esc | One step back: what you typed after sending → edit (the instruction back at the caret, to change and send again) → dropped (a selection taken from the app goes back instead). While it works, Esc stops it. A drop says so: "dropped · Shift+Esc restore" |
| Shift+Esc | Bring back what Esc dropped (an instruction, or a reply), or an exchange you left by switching windows |
| Switching windows | Your words go in as typed; a sent instruction's exchange is held for that text box. Back in it, a pill says what is waiting ("3 drafts ready · Shift+Esc open"); it takes no keys, and expires after ten minutes |
| F8 (compose) | Also send a picture of the focused window with this instruction (see [Window pictures](configuration.md#window-pictures)) |
| Tab with a selection (compose) | With nothing composed, the selected text becomes your words, and Tab asks for its rewrite as above; Esc twice puts it back. macOS, Qt apps on Linux, and the demo (GTK apps do not report selections to input methods) |
| Backspace | Edit the composition; with a rewrite showing, the first Backspace closes it |

Where you want no suggestions at all, switch that app to your usual keyboard;
the system remembers it per app or window once you turn that on: Windows,
Settings → Time & language → Typing → Advanced keyboard settings → "Let me use a
different input method for each app window"; macOS, Settings → Keyboard → Input
Sources → "Automatically switch to a document's input source"; GNOME Tweaks →
Keyboard → "Switch input sources individually for each window".

A composition is edited at its end. Navigation keys and Ctrl/Alt/Win shortcuts pressed while
composing commit your words first; on Windows the first such key is consumed, so press it again.
Characters typed with AltGr (Ctrl+Alt) stay in the composition.

Every platform shows an answer as it arrives (on Windows, Claudish's own PIME,
platforms/windows/pime, calls back when it does). The composition is limited to 512
characters. When cd_AI's service does not answer (stopped, or just after a laptop wakes), the
panel says "cd_AI is offline" from your first key.

## Browser demo

With the launcher running, open **http://127.0.0.1:18765**. The demo is the
input method, drawn in the page: one editor with an input-source badge, the
composition at the caret, and the panel, drawn with the same kit as the design lab
(`/design.html`) and the desktop adapters. It opens in compose (Tab
offers a rewrite, Enter sends it as an instruction and offers drafts to choose
with ↑↓ and take with Tab, Shift+Enter keeps your words); a Shift tap or the badge switches to continue (keys go straight in;
pause after a word and the rest waits in grey; Tab takes it). The installed input method starts in compose too. A key strip lights the keys as you use them, and each sample
types itself in its own mode. No input method installation is needed. The theme
toggle follows the system by default.

The page calls the same service as the desktop adapters. If your browser runs on another
machine, forward TCP port **18765** (the VS Code Ports tab or SSH), then open the
forwarded localhost URL. Keep the local port at 18765.

For a model-free UI demo: `python -m claudish serve --backend rules`, then open
the same URL. The page labels this as rules mode.

From a second terminal:

```sh
python -m claudish rewrite "This is very important."
python -m claudish bench --runs 12
```

To use a llama-server that is already running:

```sh
python -m claudish serve --model-url http://127.0.0.1:18766
```

## Static demo: the model in your browser

It runs at [claudish.io/demo](https://claudish.io/demo/), under the [project home page](https://claudish.io) (`site/`: what Claudish is, the keys, and an install prompt to paste into a coding agent). `.github/workflows/pages.yml` deploys both on every push to `main` (`python scripts/build_static_demo.py --site`). `python scripts/build_static_demo.py` alone writes `dist/demo/`, the same browser demo
with the model running in the page through [wllama](https://github.com/ngxson/wllama)
(llama.cpp compiled to WebAssembly). It needs no inference server, so any static
host can serve it. Nothing is downloaded until the visitor clicks **Run the model
in this browser**; the 491 MB model (pinned Qwen2.5 0.5B) is then cached by the
browser. A small service worker (`coi-sw.js`)
supplies the cross-origin isolation headers static hosts cannot set, so the
multi-threaded build runs: on the Spark's CPU in headless Chromium, a rewrite
takes about 1 s (9 s single-threaded). Browsers with WebGPU are faster still.

## Recent requests

`claudish recent` shows the service's last few requests: the mode and the text
box, which profile and backend answered, what was
consulted, the exact system prompt and turn the model received, the outcome,
and the time it took (`--full` prints the prompts whole).

## In a terminal

A terminal prompt is a text box too. After a command fails, in compose (where cd_AI starts) type
what you want ("fix", or "undo the last commit but keep the changes") and press Enter: the instruction goes with the last lines of what the
terminal shows, and the answer is a command line, placed at the prompt like
typed text. Running it is your Enter.

cd_AI reads the screen through the accessibility APIs screen readers use (AT-SPI
on Linux, UI Automation on Windows, the AX API on macOS), when you press
Tab or Enter in compose (continue stays quiet in terminals). On macOS the service's Python needs
the Accessibility permission; on Linux the desktop's accessibility bus must run
(GNOME and KDE run it). The lines go to the profile's model. A profile's `"read_terminal": false` turns reading off.
Verified with GNOME Terminal, Windows Terminal, the classic Windows console, and
Terminal.app.

**Known gap, macOS Terminal:** Terminal.app gives an input method Tab, the arrows and
Esc only while there is marked text. An instruction stays marked while its drafts show,
so they work there; continue's suggestion is not marked text, so Tab completes in the
shell instead of taking it (ROADMAP G50).

On [`benchmarks/eval/fix_cases.json`](../benchmarks/eval/fix_cases.json), 30
cases (23 need a fix, 7 are legitimate commands that failed for environmental
reasons and should be left alone), "fix" at a terminal showing the failed
command:

| Model / Q4_K_M | Fixed | Wrong | Left alone | Harmful | Median |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3 30B-A3B Instruct 2507 | 20 / 23 | 3 | 3 / 7 | 4 | 1.0 s |
| Qwen2.5 1.5B Instruct | 7 / 23 | 16 | 6 / 7 | 1 | 0.4 s |

The cases carry no error output for the legitimate commands, so a model sees
only the command and guesses; on a real screen it sees what went wrong.
Reproduce with `python benchmarks/evaluate_terminal.py --label NAME` against a
model server (the Spark, CPU llama.cpp b11822).

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
  asks in the panel: what would run, in full; nothing is highlighted, ↓ then Enter
  chooses (Deny comes first).

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

Windows (Claudish's PIME) reports the app, the field's input scope and the text around the
caret; macOS reports no field kind.

