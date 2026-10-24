# Contributing to Claudish

Claudish is a compact codebase: about 5,400 lines of Python in `claudish/` and 2,700 in three
platform adapters (`platforms/`). Most changes touch one layer. This guide shows how to get set up,
where things live, which checks prove a change works, what to pick up, and what a useful bug report
contains.

## Getting set up

```sh
git clone https://github.com/noobpwnftw/claudish && cd claudish
python3 -m venv .venv && .venv/bin/python -m pip install -e ".[claude,mcp]"
.venv/bin/python scripts/check.py      # the merge gate, about six seconds
```

Python 3.10 or newer. Without the `[claude,mcp]` extras the tests that need those SDKs are skipped,
and check.py says so. The settings page check needs Playwright with Chromium
(`--browser-python` names a Python that has it).

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
  also runs inside PIME's own Python on Windows (3.12), with no third-party packages.
- **`claudish/client.py`** is one background worker per adapter. It debounces
  (180 ms), coalesces, and never blocks an input event.
- **`claudish/server.py`** is the loopback HTTP service: `/suggest` and `/health`,
  plus the browser demo in `claudish/web/`.
- **`claudish/model.py`** has the `Rewriter`, its backends, and the default
  template. **`modes.py`** holds the invocation modes (rewrite, continue,
  instruct); **`context.py`** holds the context providers (file, command, MCP,
  caret text); **`config.py`** loads profiles.
- **`claudish/screen.py`** reads a focused terminal through the accessibility APIs (G35);
  **`capture.py`** takes the window picture F8 asks for.
- **Instructions and agents:** **`turn.py`** answers one instruction (tools in **`tools.py`**),
  **`conversation.py`** keeps a text box's turns, **`sessions.py`** and **`agent.py`** run an agent
  CLI (Claude Code) as a session, and **`textbox.py`**/**`textbox_mcp.py`** give it the text box.
- **Setup and settings:** **`setup.py`** (`claudish setup`), **`doctor.py`**, **`service.py`** (the
  login service), **`settings.py`** and **`keys.py`** (the settings page and where keys are kept),
  **`mcp_setup.py`**.
- **`platforms/linux/engine.py`** (IBus), **`platforms/windows/claudish/`**
  (PIME/TSF), and **`platforms/macos/controller.py`** (InputMethodKit) translate
  key events. Keep them thin: logic shared by all three belongs in
  `composition.py`.

The guarantees every change must keep: typed text is never lost; a candidate is
only offered, and accepted explicitly (Tab); a stale result never replaces newer
text; a failure leaves your wording available; secure fields are bypassed; and
typed text goes only to a backend the user configured. No model ships: the user picks one.

## Checks

`python scripts/check.py` runs the unit tests, compile, diff check, IBus and PIME smokes, and the
settings page in Chromium, each in under 5 seconds (about six in all), and reports PASS, FAIL, or
SKIP with a reason. It is the merge gate. A test workflow slower than that is not one we run: make
it faster or drop it. Real typing on Linux, Windows and macOS is checked by hand.

Windows' PIME is built from source with `platforms/windows/pime/make_source.sh` and, on Windows
with the Visual Studio C++ tools (`buildtools.ps1`), `build-pime.ps1`.

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
  `tests/test_macos_adapter.py`, `tests/ibus_smoke.py` and `tests/pime_smoke.py`, then type it by
  hand on each OS.

## Picking something up

Open goals are in [ROADMAP.md](ROADMAP.md), each with what "done" means; the queued ones not marked
for the owner are free to take. Say in an issue what you mean to do before a large change. A pull
request needs `scripts/check.py` to pass, and a note of what you checked by hand on which OS.

The project is maintained by an AI agent (Claude Code) under the owner's direction. Its working
files are in the repository, so its decisions are on record: [AGENT.md](AGENT.md) (its mandate and
rules), [AGENT_STATE.md](AGENT_STATE.md) (where the work stands), and `CLAUDE.md` (which points the
agent at AGENT.md). It reviews pull requests against the same gate and the guarantees above.

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
