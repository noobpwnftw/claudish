# Develop

How Claudish is built and tested. See also [CONTRIBUTING](../CONTRIBUTING.md) and the [roadmap](../ROADMAP.md).

## Testing

`python scripts/check.py` is the merge gate (unit tests, the IBus and PIME smokes, the settings
page in Chromium; each step under 5 s). Installs are checked on each OS:

- **macOS:** macOS 26 on Apple silicon, in a UTM VM: the package installs, and after a logout "ok"
  + Tab rewrites in TextEdit; cd_AI stays enabled and its service comes back after a restart; the
  offline panel. Earlier, 12 typing scenarios; event-routing tests with Cocoa test doubles.
- **Windows:** Windows 11 ARM64 in a KVM VM: install, restart, update over it, restart; "ok" + Tab
  rewrites in Notepad each time, and cd_AI installs beside PIME's Chewing. Earlier, classic Notepad
  15/15, Edge 14/14 (a shortcut right after a cleared field could lose the composed word), Windows
  Terminal and the classic console 4/4. x64 hardware is untested.
- **Linux:** the one-line installer in a clean Ubuntu 24.04 container. The Docker rig below checks
  real IBus typing with GTK and Qt on X11 (2026-10-25). GNOME Shell 46 on Wayland was checked before
  2026-10-24; KDE is not yet tested. On GNOME, a composition left in a field when you click another
  one lands in the field you clicked: GNOME commits it after GTK has moved focus, as for every
  input method.
- **Browser demo:** tested with real inference in Chromium.

## Implementation

The installable Python package is `claudish-ime` (`pyproject.toml`); its command is `claudish`.
Its core uses the standard library. The Anthropic and MCP SDKs are optional extras; platform
packages supply their native dependencies. The source inventory:

| Area | Source | Responsibility |
| --- | --- | --- |
| Typing state | `claudish/composition.py` | Composition, revisions, candidates, acceptance, focus and the held exchange |
| Delivery | `claudish/client.py`, `server.py` | Coalescing background worker, loopback requests, settings and session events |
| Models | `claudish/model.py`, `warm.py`, `children.py` | API/command/rules backends, subscription CLI lifecycle and child processes |
| Wording | `claudish/templates.json`, `modes.py`, `turn.py` | Tone, prompts, examples, field context and output handling |
| Instructions | `claudish/conversation.py`, `sessions.py`, `agent.py`, `handoff.py` | Turns, tools, questions, helper handoffs and CLI sessions |
| Context | `claudish/context.py`, `tools.py`, `textbox*.py`, `screen.py`, `capture.py` | Providers/tools, surrounding text, terminal text and F8 pictures |
| Onboarding | `claudish/setup.py`, `settings.py`, `keys.py`, `doctor.py`, `service.py`, `config.py` | Install steps, model choice, first rewrite, config, diagnosis and login service |
| Linux | `platforms/linux/` | IBus engine, registration and GNOME Shell panel |
| macOS | `platforms/macos/` | InputMethodKit controller, native panel, build and installer |
| Windows | `platforms/windows/` | PIME adapter, pinned PIME/libIME2 patches and installer |
| Browser | `claudish/web/`, `site/`, `scripts/build_static_demo.py` | Settings, design lab, browser inference and project site |
| Evidence | `tests/`, `benchmarks/`, `docs/cd_AI*.gif` | Regression checks, typing rig, measured model outputs and VM recordings |
| Maintenance | `AGENT.md`, `AGENTS.md`, `CLAUDE.md`, `ROADMAP.md` | Shared instructions, agent entry points and the ordered queue |

All three adapters use the same composition state. Input events do not wait for inference, and
every edit invalidates the previous candidate. Generated `claudish/web/lab-states.js` comes from
`scripts/lab_states.py`, which drives that same state; edit its generator rather than its output.

`docs/research/` records earlier design reviews; `benchmarks/` records model runs with their
conditions. Neither is a current release certification. `models/`, `.tools/`, `dist/`, local VM
helpers and `AGENT_STATE.md` are working material outside Git. Keep that material available for
the rigs; it is not part of the shipped source.

## Current evidence and next checks

As of 2026-10-25, the product has native typing recordings and repeatable checks, but no published
release. The merge gate runs 269 unit tests, both adapter smokes and the settings browser check.
The browser check includes subscription startup/failure/retry, a first rewrite and stale example
responses, including a delayed Settings session before controls become usable. CLI protocol tests
use stand-ins; they do not establish account access. Concurrent HTTP saves also check that a
slow model selection preserves a tone saved from another window. Separate browser runs through the real logged-in Claude Code/Haiku and Codex backends produced Settings rewrites in
2.61 s and 2.08 s on 2026-10-25 (one request each, not a latency benchmark). Settings and the site were checked
at 320, 560, 1024 and 1440 px in both themes without horizontal overflow.

The TextEdit recording shows a rewrite accepted with Tab. The Terminal recording shows a typo
question, the handoff command inserted at the prompt, Claude Code starting in the invoice project,
and its fix passing the fixture's test. These are actual Mac VM captures. Windows ARM64 has
install/update/restart and six instruction/focus/tool flows checked; Linux has the six Docker
typing scenarios below.

The macOS Apple-silicon package and Windows ARM64 installer were rebuilt from `04cac81` on
2026-10-25, update-installed and checked again after reboot. Installed Settings produced a real
rewrite through Claude Code on macOS (3.22 s, one request) and the Gemma API in Windows Edge.
TextEdit and Notepad both previewed `ok` on Tab and inserted the result on a second Tab. These
were existing rig accounts, with working model access; they do not establish a fresh-account or
browser-download install. Windows has no subscription CLI installed, so its subscription path
remains unchecked. The macOS rig now selects Claude Code; its other profiles remain available.

Candidate packages, source commit, SHA-256 hashes and screenshots are retained locally in
`dist/candidates/04cac81/manifest.json` and its adjacent `evidence/` directory. They are not
published downloads. A separate isolated source-service check with no config or credentials
confirmed that Settings opens and a rewrite reports the missing model/key.

The next checks, in order, are in [ROADMAP.md](../ROADMAP.md). In particular:

- Repeat installation and model selection on fresh accounts, then a Settings rewrite and native
  acceptance after restart/login. Exercise a Windows subscription when a logged-in CLI is present.
- Integrate the release preparation with current main and check the download/install path.
  A funded Anthropic-key rewrite and its failure states remain unchecked on the installed Mac
  and Windows packages; publishing requires the owner.
- Check Windows x64, both native panel themes against the design lab, and current Wayland
  behavior. The documented macOS Terminal continue/Tab limitation remains.

The browser demo keeps its pinned Qwen2.5 0.5B model, selected from candidates that fit browser
constraints. Model size, loading time and speed matter alongside quality there. The broader
[G53 study](../benchmarks/README.md#choosing-the-models-g53-2026-10-24) includes CPU and browser
timings as well as quality; its [current choices](../benchmarks/README.md#current-choices) explain
the different decisions. Revisit the browser choice only with a better measured tradeoff.
The native recordings complement the interactive demo.

## Build the tested CUDA backend

The measured llama.cpp commit is
`0693dbfb915f33233818373b5f6969396658d02c`. On a DGX Spark (GB10), with CUDA 13 and CMake:

```sh
git clone https://github.com/ggml-org/llama.cpp.git .tools/llama.cpp
git -C .tools/llama.cpp checkout 0693dbfb915f33233818373b5f6969396658d02c
cmake -S .tools/llama.cpp -B .tools/build -G Ninja -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=121 -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build .tools/build --target llama-server -j 8
```

Architecture `121` is specific to GB10. Use your GPU's CUDA architecture on
other hardware, or a suitable upstream binary. Code is MIT licensed; model weights,
llama.cpp and PIME retain their own licenses. Their source and weights are dependencies, not part of this Git repo.

## Verify

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the architecture and how to report bugs.

```sh
python scripts/check.py   # tests, compile, IBus and PIME smokes, the settings page: about six seconds
```

Every check takes under 5 seconds; a slower test workflow is not one we run. The individual checks:

```sh
python -m unittest discover -s tests -v
python -m compileall -q claudish platforms scripts
# Linux: actual IBus bindings on a private bus, without desktop registration:
dbus-run-session -- /usr/bin/python3 tests/ibus_smoke.py
# Either OS: the pinned PIME textService.py with platforms/windows/pime/pime.patch applied
# (check.py downloads and patches it):
python tests/pime_smoke.py --pime-source /path/to/patched/python/textService.py
# The settings page in Chromium, against a service in a throwaway config directory:
python tests/settings_page.py
```

The macOS routing tests use test doubles and do not verify Cocoa, InputMethodKit, or native
application behavior. Real typing is checked by hand on each OS: a text editor, a browser, a
terminal, focus switches, selection and caret movement, shortcut keys, password fields, the service
stopped, and switching input methods. On macOS, install the package and log out and back in first.

### Linux Docker rig

Build the Ubuntu 24.04 desktop image once, then run individual typing scenarios. Each check
starts Xvfb, the real IBus engine and service, and a GTK or Qt application; it exits within five
seconds. The `rules` backend supplies the rewrite so these checks do not need a model server.

```sh
sh tests/rigs/linux/run.sh build
sh tests/rigs/linux/run.sh check compose
sh tests/rigs/linux/run.sh check bypass
sh tests/rigs/linux/run.sh check password
sh tests/rigs/linux/run.sh check focus
sh tests/rigs/linux/run.sh check offline
sh tests/rigs/linux/run.sh check qt-selection
```

The checks cover Tab accepting a rewrite, Shift+Enter keeping the original words, password
typing, a focus change during composition, keeping words when the service stops, and restoring
a Qt selection with Esc. The rig does not check a desktop panel, Wayland, or model quality.

## Debugging on macOS

`touch ~/Library/Logs/cd_AI-trace.log` before cd_AI starts makes
it log event kinds and errors there; remove the file to stop.
(`launchctl setenv CLAUDISH_TRACE` does not reach an input method that macOS or
`open -g` starts.) Exceptions
in an input method otherwise vanish into the host app's run loop. Crash reports
are in `~/Library/Logs/DiagnosticReports/Claudish-*.ips`.

## The site and the static demo

`.github/workflows/pages.yml` deploys claudish.io on every push to `main`:
`python scripts/build_static_demo.py --site` writes the home page (`site/`) with the static demo in
`demo/`. `python scripts/build_static_demo.py` alone writes the demo to `dist/demo/`. The static demo's
service worker (`claudish/web/coi-sw.js`) supplies the cross-origin isolation headers a static host
cannot set, so wllama's multi-threaded build runs: on a DGX Spark's CPU in headless Chromium, a
rewrite takes about 1 s (9 s single-threaded).

On Windows, cd_AI's PIME
([platforms/windows/pime](../platforms/windows/pime/README.md)) calls the input method back when an
answer arrives, so it shows without a key press.
