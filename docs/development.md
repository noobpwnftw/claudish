# Develop

How Claudish is built and tested. See also [CONTRIBUTING](../CONTRIBUTING.md) and the [roadmap](../ROADMAP.md).

## Where it stands

DGX Spark/GB10 used for development, 12 warm short-phrase requests took **64.8 ms
median, 85.3 ms p95**, including both local HTTP hops. These are completed
rewrite timings, not time to first token. See [measurements](../benchmarks/README.md)
for inputs, outputs, fidelity, and model comparisons.

Status:

- **Linux:** verified end to end with the real `ibus-daemon`, a GTK app, and real
  key events in containers (`scripts/check.py --desktop`): X11 (26 scenarios), and
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

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the architecture, which check to run for which change, and how to report bugs.

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
