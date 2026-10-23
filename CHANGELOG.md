# Changelog

## 0.1.0 — the first release

cd_AI is an input method that puts a language model at the caret, in every app:
switch to it like a keyboard language, type, and accept or discard what the model
offers. English goes in. Em dashes come out.

### What is in it

- **Two modes, one Shift:** continue (keys go straight in; the rest of the
  sentence waits after the caret for Tab) and compose (Tab rewrites your words
  in place, as a CJK input method converts; Enter sends them as an instruction
  and offers drafts to pick with 1–3; Shift+Enter keeps them as typed; Esc
  steps back). A Shift tap switches, as it switches English and pinyin.
- **Terminals:** an instruction typed at a terminal prompt ("fix") sees what the
  terminal shows, read through the accessibility APIs (GNOME Terminal, Windows
  Terminal, the classic console, Terminal.app); nothing is installed in the shell.
- **A private local API:** the service accepts text-box details, sessions, and
  answers only from the input methods (a per-run token in a file only you can read).
- **Input methods** for Linux (IBus), Windows (PIME/TSF), and macOS
  (InputMethodKit). Nothing is inserted until you accept it; password fields
  bypass Claudish.
- **Bring your own intelligence:** a small local model by default (llama.cpp and
  Qwen2.5 0.5B, both pinned and SHA-256 verified), or Claude with your API key,
  any OpenAI-compatible server, or an agent CLI. Hosted backends are labelled.
- **One-command setup:** `python -m claudish setup` (config, MCP import,
  llama.cpp, the model, the input method, start at login, then `doctor`). Steps
  already done are skipped; `--dry-run` shows the plan.
- **`claudish doctor`** checks the whole chain and prints a fix for each problem;
  **`claudish service`** starts Claudish at login (systemd, a logon task, launchd).
- **Context:** files, commands, and MCP servers, per app ("supported text
  boxes"); `claudish mcp import` brings in the servers you already use with Claude.
- **Instruct, further:** several readings to pick with 1–3; F8 adds a picture of
  the window you are typing in (for vision models); read-only MCP tools the model
  may call before drafting; agent sessions whose permission questions arrive as
  choices in the candidate list (first slice).
- **`claudish fix`:** the last failed shell command, corrected.
- **The browser demo** at [claudish.io/demo](https://claudish.io/demo/): the
  model runs in the page; nothing you type leaves it.

### Install

Paste the prompt from [claudish.io](https://claudish.io/#install) into a coding
agent, or:

```sh
git clone https://github.com/noobpwnftw/claudish
cd claudish
python3 -m claudish setup
```

Python 3.10+ is required. On Windows, install [PIME](https://github.com/EasyIME/PIME)
first (setup says how); on Windows on ARM, also the x86 VC++ runtime.

### Tested, and how

- Linux: real IBus and GTK typing in a container (21 scenarios), and `setup` plus
  the login service under a real systemd user manager.
- Windows 11 ARM64 (a KVM VM): Notepad 9/9 and Edge 8/8 typing scenarios, and
  `setup` end to end.
- macOS: event tests with Cocoa doubles and a bundle build in CI; not yet run on
  a Mac.
- Measurements are from one machine (DGX Spark): about 33 ms median per short
  local rewrite on its GPU. They are not claims about your hardware.

### Known issues

- Edge on Windows: a Ctrl shortcut right after a cleared field can lose the
  composed word.
- Windows shows an agent's question at your next key press (F6).
- Not yet tested: Wayland/GNOME and Qt on Linux, x64 Windows hardware, a real
  Mac, the Claude backend against the live API, and agent sessions with Claude
  Code itself (tested with a stand-in that speaks its protocol).

Claudish is an independent, MIT-licensed project, not affiliated with or
endorsed by Anthropic.
