# Develop

How Claudish is built and tested. See also [CONTRIBUTING](../CONTRIBUTING.md) and the [roadmap](../ROADMAP.md).

## Testing

`python scripts/check.py` is the merge gate (unit tests, the IBus and PIME smokes, the settings
page in Chromium; each step under 5 s). Installs and real typing are checked by hand on each OS
([Verify](#verify)).

## Implementation

The installable Python package is `claudish-ime` (`pyproject.toml`); its command is `claudish`.
Its core uses the standard library. The Anthropic and MCP SDKs are optional extras; platform
packages supply their native dependencies. The source inventory:

| Area | Source | Responsibility |
| --- | --- | --- |
| Typing state | `claudish/composition.py` | Composition, revisions, candidates, acceptance, focus and the held exchange |
| Delivery | `claudish/client.py`, `server.py` | Coalescing background worker, loopback requests, settings and session events |
| Models | `claudish/model.py`, `warm.py`, `children.py` | API/command/rules backends; `warm.py` keeps Claude Code and Codex running beside the service; child processes |
| Answers | `claudish/shapes.py`, `quirks.py` | The answer's shape (`{"drafts": [...]}`) and its schema per backend; the quirks of plain-text answers from backends without a schema |
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

```
app ⇄ OS input framework ⇄ adapter ──(HTTP, loopback)──▶ service ──▶ backend
       IBus / TSF / IMK     platforms/*   client.py       server.py    model.py
                            composition.py
```

All three adapters use the same composition state (`composition.py`, which also runs inside
PIME's own Python on Windows, 3.12, with no third-party packages); keep the adapters thin. Input
events do not wait for inference: `client.py` is one background worker per adapter that debounces
(180 ms) and coalesces, and every edit bumps a revision, so a result for an older one is dropped. Generated `claudish/web/lab-states.js` comes from
`scripts/lab_states.py`, which drives that same state; edit its generator rather than its output.

`docs/research/` records earlier design reviews; `benchmarks/` records model runs with their
conditions. Neither is a current release certification. `models/`, `.tools/`, `dist/`, local VM
helpers and `AGENT_STATE.md` are working material outside Git. Keep that material available for
the rigs; it is not part of the shipped source.

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

See [CONTRIBUTING.md](../CONTRIBUTING.md) for what to pick up and how to report bugs.

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

The checks cover Tab accepting a rewrite, Enter keeping the original words, password
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
cannot set, so wllama's multi-threaded build runs.

On Windows, cd_AI's PIME
([platforms/windows/pime](../platforms/windows/pime/README.md)) calls the input method back when an
answer arrives, so it shows without a key press.
