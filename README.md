# cd_AI — Claudish

English goes in. Em dashes come out.

**[Try it in your browser](https://claudish.io/demo/)**: the model runs in the page; nothing you type leaves it.

An input method for Linux (IBus), Windows (PIME/TSF), and macOS
(InputMethodKit) that puts AI at the caret of every app. It works in three
layers, one per mode; F7 switches between them while you type. Switching from
en_US to cd_AI starts in the second: you type as usual, keys go straight in, and
AI only appears as a suggestion you can ignore.

1. **Translation**, which is what an input method does. Keystrokes go in and text
   comes out in another language; here, the language is Claudish: polished,
   slightly excessive English with a fondness for em dashes. (`rewrite`)
2. **Autocomplete**, which is what Copilot promised and language models are, at
   heart. Your typing goes straight into the app; pause, and the rest of the
   sentence appears after the caret. Tab takes it; keep typing to ignore it.
   (`continue`)
3. **Instruction**, which is how you work a machine. Type "write a story about a
   cat"; the input method holds it, Enter sends it to the AI, and the result
   comes back at the caret, in a text editor, a browser, or a terminal.
   (`instruct`)

Every result is only a candidate: Tab, or Enter in instruct mode, puts it in
your app, and your own wording is always one key away. The AI behind it is your
choice: a small local model (the default), any OpenAI-compatible server, Claude,
or an agent CLI such as `claude -p`, which makes the input method that agent's
text box in every app. Context such as files, command output, or MCP servers
can go along. `cd_AI` is the input method's label; no custom OS locale is
needed.

The default model is Qwen2.5-0.5B-Instruct Q4_K_M, a 491 MB download. On the
DGX Spark/GB10 used for development, 12 warm short-phrase requests took **64.8 ms
median, 85.3 ms p95**, including both local HTTP hops. These are completed
rewrite timings, not time to first token. See [measurements](benchmarks/README.md)
for inputs, outputs, fidelity, and model comparisons.

Status:

- **Linux:** verified end to end with the real `ibus-daemon`, a GTK app, and real
  key events in containers (`scripts/check.py --desktop`): X11 (25 scenarios), and
  GNOME Shell 46 on Wayland, headless, with IBus started by the shell and keys typed
  through Mutter's RemoteDesktop API (10 scenarios); plus `claudish service` under a
  real systemd user manager. Qt apps and KDE are not yet tested. On GNOME, a
  composition left in a field when you click another one lands in the field you
  clicked: GNOME commits it after GTK has moved focus, as for every input method.
  Your words survive exactly once; Enter or Esc before you click keeps them in place.
- **Windows:** verified on Windows 11 ARM64 in a KVM VM through PIME/TSF: classic
  Notepad 9/9 typing scenarios, Edge 8/8 with one known issue (a shortcut right
  after a cleared field can lose the composed word). x64 hardware is untested;
  CI runs the unit tests on Windows.
- **macOS:** covered by event-routing tests with Cocoa test doubles and a native
  bundle build in CI; not yet run on a Mac.
- **Browser demo:** tested with real inference in Chromium.

## Quick start

**One command:** with Python 3.10+, from this checkout:

```sh
python -m claudish setup
```

It shows each step and asks before doing it: write a config, import MCP servers
from your Claude setup, download a pinned llama.cpp build and the model (both
SHA-256 verified), register the input method, start Claudish at login, then run
`doctor`. Steps already done are skipped, so it is safe to run again.
`--dry-run` shows the plan, `--yes` does it all, and `--profile claude` sets up a
hosted profile instead (no model download). Installing the input method on
Windows and macOS needs an administrator, so setup prints that command. Verified
end to end on Ubuntu 24.04 under systemd in a container (`tests/desktop/linux-systemd`).

Or step by step:

1. **Try the three layers in your browser.** With Python 3.10+:

   ```sh
   python scripts/download_llama.py
   python scripts/download_model.py small
   python scripts/start.py
   ```

   Open http://127.0.0.1:18765, then switch between Rewrite, Continue, and
   Instruct. Each mode has its own sample phrases. No model handy? `python -m
   claudish serve --backend rules` runs the demo with simple stand-ins.
2. **Pick a brain.** `python -m claudish init` writes `~/.config/claudish/config.json`
   with four profiles: `local` (the default), `ollama` (any OpenAI-compatible
   server), `claude` (your API key), and `agent` (an agent CLI such as
   `claude -p`). Choose one with `python -m claudish serve --profile NAME`.
3. **Install the input method** for [Linux](#linux-input-method),
   [Windows](#windows-input-method), or [macOS](#macos-input-method), and add
   **cd_AI — Claudish** in your input sources.
4. **Start it at login.** `python -m claudish service install` runs the local
   stack (model and service) at every login: a systemd user unit on Linux, a logon
   task on Windows (no console window), a launch agent on macOS. Use
   `service install --serve -- --profile claude` for another profile, `service
   status` and `service uninstall` to inspect or remove it, and `--dry-run` to see
   what it would do.
5. **Check the setup.** `python -m claudish doctor` walks the whole chain (model,
   service, config, the input method's registration on your OS, and context
   sources) and prints a fix for anything wrong. On Linux, for example, it
   catches a session that started before the installer's search-path change
   ("log out and back in"); on Windows on ARM, PIME's missing x86 runtime.
6. **Learn four keys.** Everything else is typing.

| Key | Does |
| --- | --- |
| F7 | switch layer: continue → instruct → rewrite |
| Tab | accept the candidate; in continue, take the rest of the sentence (with nothing offered, Tab is the app's) |
| Enter | the app's in continue; send, then insert (instruct); keep your wording (rewrite) |
| Esc | keep what you typed |
| F8 | in instruct, also send a picture of the window you are typing in |
| 1–3 | when an instruction comes back as a numbered list, insert that reading; when an agent asks, answer |

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

## Start the model and service

Python 3.10+ runs the service. It has no pip runtime dependencies. Run commands
from this project directory.

Both download scripts use only the standard library and verify before installing;
an interrupted download leaves nothing behind, and a verified file is not
downloaded again. `download_llama.py` fetches a pinned
[llama.cpp](https://github.com/ggml-org/llama.cpp/releases) release build
(`b11822`, 12–24 MB) for your OS and CPU into `.tools/`, checked against the
SHA-256 GitHub publishes for it: the CPU build runs everywhere and uses Metal on
Apple silicon; `--variant vulkan` uses most GPUs on Linux and Windows.
`download_model.py` fetches the pinned upstream revision of the model into
`models/`, checked against the tested file's size and SHA-256. Set `HF_ENDPOINT`
to use a mirror.

```sh
python scripts/download_llama.py
python scripts/download_model.py small
python scripts/start.py
```

`start.py` uses `llama-server` from your `PATH` first, then the downloaded build;
pass `--server /path/to/llama-server` (`llama-server.exe` on Windows) to use
your own build, for example one with CUDA. On the Spark's CPU, the downloaded
CPU build takes a median 82 ms per short rewrite (4 threads, warm). The service listens on `127.0.0.1:18765`; the model listens
on `127.0.0.1:18766`. Ctrl+C stops both processes. Nothing is installed at startup.

This checkout already contains both GGUF models and a CUDA-enabled llama.cpp
build under the ignored `models/` and `.tools/` directories. On this Spark:

```sh
python3 scripts/start.py
```

## Browser demo

With the launcher running, open **http://127.0.0.1:18765**. The demo is the
input method, drawn in the page: one editor with an input-source badge, the
composition at the caret, and a candidate window, following the same rules as the
desktop adapters. It starts in continue (keys go straight in; pause after a word
and the rest waits in grey; Tab takes it). F7 or the badge switches to instruct
(Enter sends; pick a draft with 1–3) and rewrite (Tab takes the rewrite, Enter
keeps your words). A key strip lights the keys as you use them, and each sample
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

## Backends and rewrite templates

Claudish supplies the plumbing: the input method, a rewrite template, and the
service between them. The model is your choice, and how well it follows the
template depends on that model. `benchmarks/evaluate.py` measures any backend
on the same cases.

Use any OpenAI-compatible server and any model, such as llama.cpp, vLLM, Ollama,
LM Studio, or a hosted endpoint:

```sh
python -m claudish serve --backend openai --model-url http://127.0.0.1:11434 --model qwen2.5:7b
# A remote endpoint, with a key read from an environment variable that you name:
python -m claudish serve --backend openai --model-url https://api.example.com \
    --model some-model --api-key-env EXAMPLE_API_KEY --timeout 10
```

Or use Claude through the official SDK. It is an optional dependency. The
credentials are yours: set `ANTHROPIC_API_KEY`, or run `ant auth login`.

```sh
pip install "claudish-ime[claude]"
python -m claudish serve --backend claude                     # claude-opus-5-5
python -m claudish serve --backend claude --claude-model claude-haiku-5-5
```

The Claude backend runs one request at a time, uses low effort, and turns on
server-side refusal fallbacks (except on Haiku, which has none). It never
offers a declined or truncated rewrite; your wording stays. Typed text goes
only where you point the service. A non-loopback `--model-url` and the Claude
backend are reported as `"hosted": true` in `/health`, and the browser demo
labels them as hosted. Local inference remains the default.

Replace the rewrite template with `--prompt FILE` for any backend:

```json
{"system": "Rewrite, do not reply. Keep names and numbers exactly. Use an em dash.",
 "examples": [["the server is down", "The server is down—currently, and regrettably, unreachable."]]}
```

### Supported text boxes

The input method knows which app has focus. On Linux, IBus reports the program
(`gtk3-im:firefox` arrives as `firefox`). On macOS it is the bundle identifier
(`com.apple.Terminal`); on Windows, the program file (`notepad.exe`).
`bindings` attach context to apps:

```json
{"profiles": {"work": {"backend": "claude", "bindings": [
  {"app": "firefox*", "context": [{"type": "mcp", "name": "PR diff", "command": ["github-mcp-server", "stdio"],
                                   "tool": "get_pull_request_diff", "arguments": {"owner": "me", "repo": "app", "pullNumber": 42}}]},
  {"app": "com.apple.Terminal", "context": [{"type": "command", "command": ["git", "status", "--short"]}]}
]}}}
```

In a bound app, Claudish reads that context and the model or agent works with
it. Everywhere else it is a plain input method. Patterns are case-insensitive
globs. Every response lists what was `consulted`, so it is always visible what
the AI read. Support grows by adding context providers per app, not by
installing another app.

### An agent CLI as the backend

An agent CLI is a text box and Enter, and an input method is a text box in every
app. With `"backend": "command"`, the input method becomes that CLI's text box.
Claudish sends the mode's instructions, the profile's context, and your text on
stdin; the command's output becomes the candidate, which you accept with Tab:

```json
{"profiles": {"agent": {"backend": "command", "timeout": 120,
                        "command": ["claude", "-p", "--output-format", "text"]}}}
```

Any CLI that reads a prompt on stdin works: `claude -p`, `ollama run MODEL`,
`llm`, or your own script. The command comes only from your config, runs without a
shell, and never sees your text as arguments. Tool permissions are the CLI's
own; for example, Claude Code's `--allowedTools` in the command list. Agents are
slow, so the profile's `timeout` applies (`/health` reports it), and typing is
never blocked while one works. These profiles are reported as hosted unless
the profile sets `"hosted": false`.

Measured on the Spark with Claude Code 2.1.306: an instruct request ("thank
Priya for fixing the flaky CI job, it saved the release") returned a finished,
em-dashed thank-you note in 4.5 s.

### Profiles

Instead of passing flags, declare your backends once in
`~/.config/claudish/config.json` (or `$XDG_CONFIG_HOME/claudish/config.json`, or
pass `--config FILE`):

```json
{"profile": "local",
 "profiles": {
   "local":  {"backend": "llama"},
   "ollama": {"backend": "openai", "model_url": "http://127.0.0.1:11434", "model": "qwen2.5:7b",
              "prompt": "grand.json"},
   "remote": {"backend": "openai", "model_url": "https://api.example.com", "model": "some-model",
              "api_key_env": "EXAMPLE_API_KEY", "timeout": 10},
   "claude": {"backend": "claude", "claude_model": "claude-opus-5-5"}
 }}
```

`python -m claudish serve` uses the file's `"profile"`. `--profile claude`
picks another, and any flag overrides the profile's value. A template path in a
profile is relative to the config file. Keys are never stored in the file: name
an environment variable with `api_key_env`. Unknown keys, a literal `api_key`,
and wrong types are rejected at startup. `/health` reports the active profile.

### Window pictures

For apps that publish nothing Claudish can read, an instruction can carry a
picture of the window you are typing in. In instruct mode, press **F8** before
Enter: the hint shows "instruct + window picture", and the service captures the
focused window once, sends it with that one instruction, and lists it in
"consulted". Nothing is captured without F8, F8 never carries over to the next
instruction, password fields never reach Claudish, and the picture is not stored
or logged. With a hosted backend it goes to that service, as your text does.

- **Capture:** Windows uses PrintWindow (built in). Linux X11 needs `xprop` and
  ImageMagick (`sudo apt install x11-utils imagemagick`). On Wayland or macOS,
  set the profile's `"look_command"` to a program that writes a PNG of the
  focused window to stdout, such as a `grim` or `screencapture` wrapper.
- **Backends:** `claude` and any OpenAI-compatible server with a vision model.
  For llama.cpp, start a vision model with its projector, for example
  [Qwen2.5-VL-3B](https://huggingface.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF):
  `llama-server -m Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf --mmproj
  mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf -c 8192`. The `command` backend refuses.

Verified with a real capture in both places. On Windows 11 ARM64, a Notepad
invoice was captured with PrintWindow and sent to Qwen2.5-VL-3B (Q4_K_M) on the
Spark GPU; "what is the amount due here?" returned "The amount due is 1,250.00
EUR." in 0.18 s. On X11, the desktop test captures a GTK window with ImageMagick.

### Context

A profile can attach reference context that the model sees with your text: a
file such as a style guide or glossary, or any local command's output. For
example, the diff of the branch whose PR description you are writing:

```json
{"profiles": {"pr": {"backend": "claude", "context": [
  {"type": "command", "name": "branch diff", "command": ["git", "-C", "~/src/app", "diff", "main...HEAD"], "ttl": 60},
  {"type": "file", "path": "~/notes/style.md"}
], "max_context_chars": 6000}}}
```

Commands run exactly as configured, without a shell, and only from your config
file; requests cannot add them. Results are cached for `ttl` seconds (default
30). A failing or slow provider (`timeout`, default 5 s) is skipped, never
blocking a rewrite. Context goes into the system prompt, ahead of your text, so a
local llama.cpp server reuses its prompt cache while you type. Adapters may also
send the text around the caret as `before`/`after` in `/suggest`. Context goes
to the profile's backend, so with a hosted backend it leaves the machine like
your text does.

MCP servers can supply context too (`pip install "claudish-ime[mcp]"`). Claudish
starts the configured stdio server, calls one tool or reads one resource, and
caches the text:

```json
{"type": "mcp", "name": "PR diff", "command": ["github-mcp-server", "stdio"],
 "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "$GITHUB_TOKEN"},
 "tool": "get_pull_request_diff", "arguments": {"owner": "me", "repo": "app", "pullNumber": 42},
 "ttl": 120, "timeout": 15}
```

`"$NAME"` values in `env` are read from your environment, so tokens stay out of
the config file. Use `"resource": "uri"` instead of `"tool"` to read a resource.

Already using MCP servers with Claude? Bring them along:

```sh
python -m claudish mcp import            # from Claude Desktop, Claude Code (~/.claude.json), and ./.mcp.json
python -m claudish mcp list              # connect to each server; show its tools and resources
python -m claudish context test --app firefox --show   # what a binding would read in that app
```

Imported servers land under `"mcp_servers"` in your config and are used by name:
`{"type": "mcp", "server": "github", "tool": "...", "arguments": {...}}`. Secrets
are never copied: every `env` and header value becomes a `$NAME` reference, and
`import` lists the variables to set.

Apps that publish MCP on a local socket are read with `url` instead of
`command`: streamable HTTP by default, or `"transport": "sse"`. Headers may use
`"$NAME"` values from your environment:

```json
{"type": "mcp", "name": "editor", "url": "http://127.0.0.1:3920/mcp",
 "headers": {"Authorization": "Bearer $EDITOR_MCP_TOKEN"}, "tool": "get_selection"}
```

Paired with a binding, this lets an app hand its context to the input method
without knowing Claudish exists.

For a deterministic demo without a model, use `python -m claudish serve
--backend rules`. That mode performs simple word substitutions and identifies
itself as `rules` in API responses. It does not perform neural rewriting.

### Tools: instructions that look things up

Context is read before the model starts. Tools go further: an instruction may
*call* MCP tools while it works, then draft from what they returned, for example
"tell the team how CI looks on main". Name servers from `mcp_servers` in a
profile:

```json
{"profiles": {"agent": {"backend": "llama", "timeout": 60,
  "tools": ["github", {"server": "notes", "trust": ["pull_request_diff"]}]}}}
```

- Only tools the server marks read-only (`readOnlyHint`) are offered, plus the
  ones you vouch for with `"trust"`. Tools with side effects are never offered;
  they will need a per-call approval in the candidate list (G18).
- Every call appears in "consulted", such as `notes.ci_status(branch="main")`.
- The loop is bounded: at most 4 rounds of calls, and 60 s in all. The result is
  still only a candidate.
- It needs an OpenAI-compatible server whose model calls tools (llama.cpp, whose
  chat templates handle tool calls by default, vLLM, Ollama). On the Spark, Qwen2.5-14B called the right tool and
  drafted from its result ("41 tests have passed… test_upload_retry timed out
  after 30 seconds", 3.1 s), and called none for a haiku. Qwen2.5-1.5B never
  called a tool and wrote around the gap. Claude and agent CLIs come later; an
  agent CLI behind the `command` backend already uses its own tools.

### Agent sessions: an agent at the caret

With `"session_command"` in a profile, a sent instruction (instruct mode, Enter)
runs an agent instead of a single model call. Claudish is the agent's host: its
progress and partial draft show in the input method's status line, its
permission questions become the candidate list, and its final answer is a
candidate like any other. For Claude Code:

```json
{"profiles": {"code": {"backend": "llama",
  "session_command": ["claude", "--print", "--input-format", "stream-json",
    "--output-format", "stream-json", "--verbose", "--include-partial-messages",
    "--permission-prompts", "host"]}}}
```

- *"is my branch clean?"* → `Allow — Bash: git status` / `Deny`: **1** allows that one
  call, **2** denies it (the agent carries on without it). Nothing runs without
  your choice unless your own Claude Code settings already allow it.
- **Esc** at any point stops the agent and keeps your words. Editing the
  instruction stops it too.
- The agent runs with your Claude Code login, settings, and working directory
  (the service's), and its usage counts as yours. A session is limited to five
  minutes and four at a time.
- Status: tested end to end in the Linux desktop container (real IBus and GTK)
  with a scripted agent that speaks Claude Code's stream-json protocol (the
  message shapes come from the Agent SDK's control protocol), plus the PIME smoke
  and the macOS doubles. On Windows, a question shows at your next key press
  (F6). A live run against Claude Code itself is pending.

## Modes

Every request names a mode, and every mode only offers a candidate, which you
accept with Tab or ignore:

| Mode | You type | The candidate |
| --- | --- | --- |
| `rewrite` (default) | a phrase | the phrase, rewritten in house style |
| `continue` | the start of a sentence | your text plus the next few words |
| `instruct` | an instruction, such as "decline politely, propose Thursday" | the text itself, written using the profile's context |

The browser demo has a mode switch. Adapters send `"mode"` in `/suggest`, and
`/health` lists the modes. A profile can replace any mode's template or token
budget, or add a mode of its own:

```json
{"profiles": {"p": {"modes": {"instruct": {"max_tokens": 900},
                               "haiku": {"prompt": "haiku.json", "max_tokens": 60}}}}}
```

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

On [`benchmarks/eval/fix_cases.json`](benchmarks/eval/fix_cases.json), 30
cases on the Spark: 23 need a fix, and 7 are legitimate commands that failed
for environmental reasons, which must be left alone.

| Model / Q4_K_M | Fixed | Wrong | No fix | Left alone | Harmful | Median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen2.5 0.5B Instruct | 15 / 23 | 3 | 5 | 6 / 7 | 1 | 38 ms |
| Qwen2.5 1.5B Instruct | 22 / 23 | 0 | 1 | 7 / 7 | 0 | 54 ms |

Reproduce with `python benchmarks/evaluate_fix.py --label NAME` against a model
server. The bash hook is tested; the zsh hook has not been run yet.

## Linux input method

Requires an IBus desktop and system Python with PyGObject and IBus bindings.
On Ubuntu/Debian:

```sh
sudo apt install ibus python3-gi gir1.2-ibus-1.0
/usr/bin/python3 platforms/linux/install.py            # per user, no sudo
# or, for sessions that do not read ~/.config/environment.d:
sudo /usr/bin/python3 platforms/linux/install.py --system
```

IBus only reads engine definitions from `IBUS_COMPONENT_PATH`, which defaults to
`/usr/share/ibus/component`. The per-user install therefore writes
`~/.config/environment.d/90-claudish-ibus.conf` to add `~/.local/share/ibus/component`.
systemd-managed sessions, including GNOME, apply it at the next login. The
installer does not change the active keyboard. Log out and back in, then add
**English → cd_AI — Claudish** to Input Sources and select it with your input-source
shortcut while the service is running. The engine keeps your keyboard layout, so
AltGr and dead keys still work. The project directory must stay at its
installed path. Remove with `install.py --uninstall` (add `--system` if you
installed that way), then log out and back in.

Wayland/X11 application coverage depends on the desktop's IBus integration.
This adapter does not support an Fcitx-only session or a raw terminal console.

## Windows input method

Install [PIME](https://github.com/EasyIME/PIME) **with its Python backend** first.
PIME supplies the native Windows Text Services Framework component. Claudish
provides a Python service loaded by that component, rather than a keyboard hook.

In an administrator PowerShell:

```powershell
.\platforms\windows\install.ps1
# For a different PIME location:
.\platforms\windows\install.ps1 -PimeRoot 'C:\Program Files (x86)\PIME'
```

This copies the plugin and shared modules into PIME's input-method directory
and re-registers its existing x86/x64 DLLs so it can enumerate the new profile.
Sign out/in and select **cd_AI — Claudish** using Win+Space. Run the model and
service in a normal user terminal. The plugin uses PIME's embedded Python;
the model/service use your separate Python 3.10+ installation.

**Windows on ARM:** use a PIME build with ARM64X support (newer than
2.0.0-beta3; the [AppVeyor master builds](https://ci.appveyor.com/project/EasyIME/pime)
have it), and install the
[x86 VC++ runtime](https://aka.ms/vs/17/release/vc_redist.x86.exe). PIME's launcher is
an x86 program; without that runtime it finds an ARM64 `vcruntime140.dll` on your
`PATH` (Python for ARM64 puts one there) and fails with error `0xc000007b`, so every
PIME input method types plain text. Verified on Windows 11 ARM64 (build 26100) in
classic Notepad: 9 typing scenarios, `tests/desktop/windows`.

To remove Claudish, remove its input profile in Windows settings, then remove
`PIME\python\input_methods\claudish`. Keep PIME itself if you use other PIME input
methods.

## macOS input method

The adapter uses Apple's [InputMethodKit](https://developer.apple.com/documentation/inputmethodkit/imkinputcontroller)
through [PyObjC](https://pyobjc.readthedocs.io/en/latest/apinotes/InputMethodKit.html).
The builder uses py2app to bundle Python, the adapter, and its shared modules
into `Claudish.app`. The model runs in a separate process as on Windows/Linux.

On a Mac with a framework build of Python 3.10+ (for example, from python.org):

```sh
python3 platforms/macos/build.py --install
```

This creates an isolated build environment, installs macOS build dependencies,
builds `dist/macos/Claudish.app`, applies a local ad-hoc signature, and copies it
to `~/Library/Input Methods/Claudish.app`. It does not change your active input
source. Omit `--install` to build only. These commands must run on macOS; the
Spark cannot build or validate a native Mac app bundle.

Log out/in, then add Claudish under **System Settings → Keyboard → Text Input →
Edit → +** (look under English). Choose it using the Input menu or your configured
input-source shortcut. Start the service separately:

```sh
python3 scripts/download_model.py small
python3 scripts/start.py --server /path/to/llama-server
```

Use a macOS llama.cpp build; Apple Silicon builds can use Metal. Mac inference
performance has not been measured. Alternatively, forward the Spark's service
to the Mac's `127.0.0.1:18765` over SSH and leave inference running on the Spark.

The candidate panel refreshes automatically; Tab accepts, Enter/Escape keeps
your wording, and F6 reopens a ready candidate. Navigation keys and Command or
Control shortcuts commit the current wording before being passed through.
Characters typed with Option, such as — and €, stay in the composition.
Composition edits currently work at the end of the buffer. Secure fields and
application-specific composition behavior need native acceptance testing.

This is a development bundle, not a notarized release installer. Distribution
to other users needs Developer ID signing and notarization. To uninstall or
replace it, switch to another input source, remove Claudish from Input Sources,
remove `~/Library/Input Methods/Claudish.app`, and log out/in. The installer
refuses to overwrite an existing installed app.

## Typing

| Key/action | Result |
| --- | --- |
| Type | Accumulate the phrase in an editable composition buffer |
| `-` | Insert `—` immediately |
| Pause for 180 ms | Request a local rewrite in the background |
| F6 | Preview a completed candidate; useful on Windows |
| F7 | Switch mode: continue → instruct → rewrite (Linux shows it in the auxiliary text, Windows in a notice). F7 belongs to the input method while cd_AI is the active input source, so apps do not receive it then |
| Continue mode | Typing goes straight into the app (the model sees it as context); after a pause the rest of the sentence appears after the caret: greyed on Linux, as marked text on macOS, and in the candidate window on Windows (F6 shows it). Tab takes it, Esc dismisses it, and typing ignores it. Tab, Enter, Backspace, and arrows are the app's when nothing is offered. A focus change only ever drops the suggestion: IBus discards commits made during focus-out, so a suggestion inside the composition would either lose your words or commit text you never accepted |
| Enter (instruct) | Send the held instruction; Enter again (or Tab) inserts the result; Esc keeps your text |
| 1–9 (instruct list) | An instruction offers up to three readings as a numbered list, as in a CJK input method; a digit inserts that one, Enter or Tab the first. While you type, digits are text. A profile sets the count per mode: `"modes": {"instruct": {"candidates": 1}}` |
| F8 (instruct) | Also send a picture of the focused window with this instruction (see [Window pictures](#window-pictures)) |
| Tab | Commit an available rewrite; if none is ready, keep composing |
| Enter / Escape | Commit your wording, including the em-dash substitution |
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

## Implementation

`claudish/composition.py` owns text, candidate, and revision. All three adapters use
it. A single background worker waits for a typing pause and coalesces pending
requests. Every edit invalidates the previous candidate; an old response cannot
replace newer text, including after composition ends.

The service calls a persistent llama.cpp model with greedy decoding, a short
style prompt, one example, and prompt caching. Network access is unnecessary
after downloading dependencies and weights. Default inference and typing traffic
stay on loopback. Typed text is not written to the service's access logs. Model
rewrites can change meaning; they are candidates accepted explicitly with Tab.
The system prompt and example are in `claudish/model.py`.

Tiny-model fine-tuning on paired original/Claudish phrases would be a useful
next step. No Claudish-specific trained weights are included or claimed here.

## Build the tested CUDA backend

The measured llama.cpp commit is
`0693dbfb915f33233818373b5f6969396658d02c`. On the Spark, with CUDA 13 and CMake:

```sh
git clone https://github.com/ggml-org/llama.cpp.git .tools/llama.cpp
git -C .tools/llama.cpp checkout 0693dbfb915f33233818373b5f6969396658d02c
cmake -S .tools/llama.cpp -B .tools/build -G Ninja -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=121 -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build .tools/build --target llama-server -j 8
```

Architecture `121` is specific to GB10. Use your GPU's CUDA architecture on
other hardware, or a suitable upstream binary. Code is MIT licensed; Qwen and
SmolLM2 weights retain their Apache 2.0 licenses; llama.cpp and PIME retain their
own licenses. Their source and weights are dependencies, not part of this Git repo.

## Verify

See [CONTRIBUTING.md](CONTRIBUTING.md) for the architecture, which check to run for which change, and how to report bugs.

```sh
python scripts/check.py           # tests, compile, IBus and PIME smokes (fetches pinned PIME source)
python scripts/check.py --model   # also: real model, rewrite, fidelity eval, browser demo
```

The individual checks:

```sh
python -m unittest discover -s tests -v
python -m compileall -q claudish platforms scripts
# Linux: actual IBus bindings on a private bus, without desktop registration:
dbus-run-session -- /usr/bin/python3 tests/ibus_smoke.py
# Either OS, with PIME's Python source available:
python tests/pime_smoke.py --pime-source /path/to/PIME/python/textService.py
```

Optional browser acceptance test, with the demo running and Playwright/Chromium
installed in your development environment:

```sh
python tests/browser_demo.py
# Or use an existing Chromium and save desktop/mobile screenshots:
python tests/browser_demo.py --executable /path/to/chromium --screenshots .tools/demo-screenshots
```

This checks actual backend inference, keyboard commits, the dash toggle,
clipboard, stale-result rejection, error recovery, and mobile overflow.

Remote CI covers Windows, Linux, and macOS, plus a macOS bundle build, native
controller import, and signature check. It is opt-in: push a `ci/*` branch or run
the workflow manually. The macOS routing tests use test
doubles and do not verify Cocoa, InputMethodKit, or native application behavior.
Native desktop acceptance should
cover a text editor, browser, terminal, focus switches, selection/caret movement,
shortcut keys, secure fields, service failure, and input-method switching.
