# Develop

How Claudish is built and tested. See also [CONTRIBUTING](../CONTRIBUTING.md) and the [roadmap](../ROADMAP.md).

## Where it stands

DGX Spark/GB10 used for development, 12 warm short-phrase requests took **64.8 ms
median, 85.3 ms p95**, including both local HTTP hops. These are completed
rewrite timings, not time to first token. See [measurements](../benchmarks/README.md)
for inputs, outputs, fidelity, and model comparisons.

Status:

- **Linux:** verified end to end with the real `ibus-daemon`, a GTK app, and real
  key events in containers (2026-10): X11 with GTK and Qt, and
  GNOME Shell 46 on Wayland, headless, with IBus started by the shell and keys typed
  through Mutter's RemoteDesktop API; plus `claudish service` under a real systemd
  user manager (the scenario counts are in the README). KDE is not yet tested. On GNOME, a
  composition left in a field when you click another one lands in the field you
  clicked: GNOME commits it after GTK has moved focus, as for every input method.
  Your words survive exactly once; Enter or Esc before you click keeps them in place.
- **Windows:** verified on Windows 11 ARM64 in a KVM VM through Claudish's
  patched PIME: classic Notepad 15/15, Edge 14/14 with one known issue (a
  shortcut right after a cleared field can lose the composed word), Windows
  Terminal and the classic console 4/4. x64 hardware is untested.
- **macOS:** real typing on macOS 26 in a UTM VM (12 scenarios, installed by its package), plus
  event-routing tests with Cocoa test doubles.
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
# Either OS, with PIME's Python source available:
python tests/pime_smoke.py --pime-source /path/to/PIME/python/textService.py
# The settings page in Chromium, against a service in a throwaway config directory:
python tests/settings_page.py
```

The macOS routing tests use test doubles and do not verify Cocoa, InputMethodKit, or native
application behavior. Real typing is checked by hand on each OS: a text editor, a browser, a
terminal, focus switches, selection and caret movement, shortcut keys, password fields, the service
stopped, and switching input methods. On macOS, install the package and log out and back in first.

## Debugging on macOS

`touch ~/Library/Logs/cd_AI-trace.log` before cd_AI starts makes
it log event kinds and errors there (never typed text); remove the file to stop.
(`launchctl setenv CLAUDISH_TRACE` does not reach an input method that macOS or
`open -g` starts.) Exceptions
in an input method otherwise vanish into the host app's run loop. Crash reports
are in `~/Library/Logs/DiagnosticReports/Claudish-*.ips`.
