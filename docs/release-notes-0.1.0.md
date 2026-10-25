# cd_AI 0.1.0

An English input method that rewrites what you compose with a language model: corporate slop by
default, four other tones, or a described one. Type, press **Tab** for the rewrite, **Tab** again to
put it in; **Shift+Enter** asks the model for drafts, and **Enter** keeps the words as typed.

## Download

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway**. With Windows' **Smart App Control** fully on (not in evaluation), an
unsigned installer is blocked with no Run anyway.

| | File | Tested |
| --- | --- | --- |
| macOS, Apple silicon | `cd_AI.pkg` | macOS 26 (VM). Intel Macs: not supported yet; the installer says so. |
| Windows 11 | `cd_AI-setup.exe` | Windows 11 ARM64 (VM): install by a standard account, restart, update, uninstall. x64: not yet tested. |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.1.0/scripts/install.sh \| sh` | A preview: installs in a clean Ubuntu 24.04. |

## The model

cd_AI ships no model. At the end of the install, its settings ask for one:

- **Claude** with an Anthropic API key (`claude-opus-5-5` by default). With a key that has no
  credit, Tab says "no credit on the Anthropic account".
- **Claude Code** for a Claude subscription, or **Codex** for a ChatGPT subscription, through
  their installed, logged-in commands. Settings follows startup and offers a retry after login.
- **Another model API**: any OpenAI-compatible address (OpenAI, OpenRouter, Groq, Ollama, LM Studio
  or llama.cpp), with a key if it needs one.

Use **Try a rewrite** in Settings before switching input methods. On 2026-10-25, installed
packages produced rewrites, drafts, answers, approvals and a Claude Code handoff on macOS (Gemma 4
as "Another model API", and Claude Code), and ran their service at login on Windows ARM64 for a
standard account. Codex produced a real rewrite from Settings run from source. Still to check:
Codex from a package, a logged-in subscription on Windows, Windows x64, browser downloads, and a
funded Anthropic API key. See [the current evidence](development.md#current-evidence-and-next-checks).

## Good to know

- Log out and back in after installing on macOS; restart on Windows. Settings… in the input menu
  opens the settings again.
- On Windows, cd_AI installs beside a PIME you already have (Chewing, Rime).
- When cd_AI's service is not running, the panel says "cd_AI is offline"; Enter keeps the words.
