# Contributing to Claudish

Claudish is a small codebase: about 1,000 lines of Python in `claudish/` plus
three thin platform adapters. Most changes touch one layer. This guide shows
where things live, which checks prove a change works, and what a useful bug
report contains.

## How a keystroke becomes a candidate

```
app ⇄ OS input framework ⇄ adapter ──(HTTP, loopback)──▶ service ──▶ backend
       IBus / TSF / IMK     platforms/*   client.py       server.py    model.py
                            composition.py                  context.py   (llama.cpp, any OpenAI-
                                                            modes.py      compatible server, Claude)
```

- **`claudish/composition.py`** holds the typed text, the candidate, the
  revision counter, and the mode. Every edit bumps the revision; a model result
  for an older revision is dropped. All three adapters share this file, and it
  must stay Python 3.6-compatible for PIME's embedded Python.
- **`claudish/client.py`** is one background worker per adapter. It debounces
  (180 ms), coalesces, and never blocks an input event.
- **`claudish/server.py`** is the loopback HTTP service: `/suggest` and `/health`,
  plus the browser demo in `claudish/web/`.
- **`claudish/model.py`** has the `Rewriter`, its backends, and the default
  template. **`modes.py`** holds the invocation modes (rewrite, continue,
  instruct); **`context.py`** holds the context providers (file, command, MCP,
  caret text); **`config.py`** loads profiles.
- **`claudish/screen.py`** reads a focused terminal through the accessibility APIs (G35).
- **`platforms/linux/engine.py`** (IBus), **`platforms/windows/claudish/`**
  (PIME/TSF), and **`platforms/macos/controller.py`** (InputMethodKit) translate
  key events. Keep them thin: logic shared by all three belongs in
  `composition.py`.

The guarantees every change must keep: typed text is never lost; a candidate is
only offered, and accepted explicitly (Tab); a stale result never replaces newer
text; a failure leaves your wording available; secure fields are bypassed; and
typed text goes only to a backend the user configured. Local is the default.

## Checks

`scripts/check.py` runs everything this machine can run and reports PASS, FAIL,
or SKIP with a reason:

| Command | Adds | When |
| --- | --- | --- |
| `python scripts/check.py` | unit tests, compile, diff check, IBus and PIME smokes (and the `[claude,mcp]` extras tests if a venv has them) | while iterating |
| `… --model` | a real llama.cpp model: rewrite, the 41-case fidelity evaluation, the Playwright browser demo | before merging |
| `… --desktop` | real typing in a container: Xvfb, the real `ibus-daemon`, a GTK app, `xdotool` keys | any adapter or installer change |

Platform coverage beyond Linux:

- **Windows:** `tests/desktop/windows` runs Windows 11 on ARM under qemu/KVM
  (`vm.sh start`, then `vm.sh sync` and `vm.sh run jobs/setup.ps1` /
  `jobs/typing.ps1`). It types into Notepad through TSF and PIME.
- **macOS:** the Cocoa-double tests run everywhere; a real bundle build runs only
  on GitHub CI. Remote CI is opt-in: push a branch named `ci/<topic>`.

Changes to templates or models are measured, not argued: `benchmarks/evaluate.py`
for fidelity, `benchmarks/judge.py` (a larger local model, calibrated against
hand labels) for meaning changes the mechanical checks miss, and
`benchmarks/evaluate_terminal.py` for instructions typed at a terminal prompt. Read the outputs, not only
the scores.

## Common changes

- **A backend:** add a branch in `Rewriter.rewrite` (`model.py`) and a
  `--backend` choice in `config.BACKENDS`. Report hosted backends through
  `Rewriter.hosted`, so `/health` and the demo can say so. Optional SDKs stay
  optional: import them lazily, and add a `pyproject.toml` extra.
- **A mode:** add a template to `modes.defaults()` and, if needed, output
  handling in `modes.finish()`. Users can also add modes from a profile without
  code.
- **A context provider:** add a type to `context.PROVIDER_KEYS` and a branch in
  `Provider.read`. Providers come only from the config file, and a failing one
  must be skipped, never fatal.
- **An adapter key:** implement it in all three adapters, and test it in
  `tests/test_macos_adapter.py`, `tests/ibus_smoke.py`, `tests/pime_smoke.py`,
  and the desktop drivers.

## Bug reports

The most useful reports say:

- the OS and version, the desktop or session type (GNOME, KDE, X11, or Wayland
  on Linux), and the application where you typed;
- the input framework version (`ibus version`, the PIME version, or the macOS
  version);
- the keys you pressed, what you expected, and what you got;
- `python -m claudish doctor --json` output, which covers the backend, the service, the
  input method's registration, and context sources, and contains no typed text.

Leave out the text you typed if it is private. A made-up phrase that reproduces
the problem is just as good. The service never logs typed text, so it cannot
leak through logs you attach.
