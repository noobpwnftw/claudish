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
- **Linux:** the one-line installer in a clean Ubuntu 24.04 container. Real typing with the real
  `ibus-daemon` (X11 with GTK and Qt, GNOME Shell 46 on Wayland) was verified in containers before
  2026-10-24; KDE is not yet tested. On GNOME, a composition left in a field when you click another
  one lands in the field you clicked: GNOME commits it after GTK has moved focus, as for every
  input method.
- **Browser demo:** tested with real inference in Chromium.

## Implementation

`claudish/composition.py` owns text, candidate, and revision. All three adapters use
it. A single background worker waits for a typing pause and coalesces pending
requests. Every edit invalidates the previous candidate; an old response cannot
replace newer text, including after composition ends.

The service sends each request to the profile's backend (`claudish/model.py`): Claude through
the SDK by default, any OpenAI-compatible server, or an agent CLI. What the model is told is in
`claudish/templates.json`. Measurements and model comparisons are in
[benchmarks](../benchmarks/README.md).

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

## Debugging on macOS

`touch ~/Library/Logs/cd_AI-trace.log` before cd_AI starts makes
it log event kinds and errors there; remove the file to stop.
(`launchctl setenv CLAUDISH_TRACE` does not reach an input method that macOS or
`open -g` starts.) Exceptions
in an input method otherwise vanish into the host app's run loop. Crash reports
are in `~/Library/Logs/DiagnosticReports/Claudish-*.ips`.
