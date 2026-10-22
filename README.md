# cd_AI — Claudish

English goes in. Em dashes come out.

A local LLM input method for Linux (IBus), Windows (PIME/TSF), and macOS
(InputMethodKit). Type a phrase
in composition, preview its polished, mildly excessive rewrite, then commit it
to the focused application. `cd_AI` is the input method's label; the underlying
language remains English. No custom OS locale is necessary.

The default model is Qwen2.5-0.5B-Instruct Q4_K_M, a 491 MB download. On the
DGX Spark/GB10 used for development, 12 warm short-phrase requests took **64.8 ms
median, 85.3 ms p95**, including both local HTTP hops. These are completed
rewrite timings, not time to first token. See [measurements](benchmarks/README.md)
for inputs, outputs, limitations, and the smaller-model comparison.

This is an initial implementation. The shared service and real model inference
have been tested on Linux. The IBus adapter passes an isolated binding smoke
test. The Windows adapter passes the upstream PIME Python request/reply
contract on Linux; native Windows installation, TSF, and application behavior
still require testing on a Windows machine. The macOS adapter has event-routing
tests using Cocoa test doubles and a native app-bundle CI job; its bundle and
desktop behavior have not been verified on a Mac here. None of the desktop
adapters has been tested end to end in a graphical application in this headless
session. The browser demo has been tested with actual inference in Chromium.

## Start the model and service

Python 3.10+ runs the service. It has no pip runtime dependencies. Run commands
from this project directory. Obtain a [llama.cpp](https://github.com/ggml-org/llama.cpp/releases)
build for your OS/GPU. Keep its DLLs/shared libraries beside its executable.

The download script uses only the standard library. It fetches the pinned
upstream revision of the model into `models/` and installs it only after its size
and SHA-256 match the tested file; an interrupted download leaves nothing behind.
A verified model is not downloaded again. Set `HF_ENDPOINT` to use a mirror.

```sh
python scripts/download_model.py small
python scripts/start.py --server /path/to/llama-server
```

On Windows, pass the path to `llama-server.exe` instead. On a CPU-only machine,
add `--gpu-layers 0`. The service listens on `127.0.0.1:18765`; the model listens
on `127.0.0.1:18766`. Ctrl+C stops both processes. Nothing is installed at startup.

This checkout already contains both GGUF models and a CUDA-enabled llama.cpp
build under the ignored `models/` and `.tools/` directories. On this Spark:

```sh
python3 scripts/start.py
```

## Browser demo

With the launcher running, open **http://127.0.0.1:18765**. The service includes
a buildless browser demo: type a phrase, pause for a rewrite, then press **Tab**
to accept it or **Enter** to keep your wording. Committed text appears below,
where you can copy or clear it. **Shift+Enter** inserts a line break. Sample
phrases, an em-dash toggle, and measured response times are included. No input
method installation is needed to try the demo; it is an in-page simulation.
The theme picker offers System, Light, and Dark. It follows the system by
default; manual choices last only for the current page, with no cookies or storage.

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
your text does. MCP context sources are next.

For a deterministic demo without a model, use `python -m claudish serve
--backend rules`. That mode performs simple word substitutions and identifies
itself as `rules` in API responses. It does not perform neural rewriting.

## Linux input method

Requires an IBus desktop and system Python with PyGObject and IBus bindings.
On Ubuntu/Debian:

```sh
sudo apt install ibus python3-gi gir1.2-ibus-1.0
/usr/bin/python3 platforms/linux/install.py
```

The installer registers a per-user component; it does not change the active
keyboard. Log out/in, then add **English → cd_AI — Claudish** to Input Sources.
Select it with your desktop's input-source shortcut while the service is running.
The project directory must remain at its installed path. To unregister, remove
`~/.local/share/ibus/component/claudish.xml`, then log out/in.

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
| Tab | Commit an available rewrite; if none is ready, keep composing |
| Enter / Escape | Commit your wording, including the em-dash substitution |
| Backspace | Edit the composition and invalidate its candidate |

Enter commits composition first; press it again to send a newline. This first
version edits composition at its end. Linux commits original wording before
forwarding navigation and shortcuts. On Windows, the first navigation key
commits composition and is consumed; press again to navigate. Ctrl/Alt/Win
shortcuts pass through to TSF and the application; characters typed with AltGr
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
