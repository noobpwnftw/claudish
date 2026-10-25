# cd_AI 0.1.0

An English input method that rewrites what you compose with a language model: corporate slop by
default, four other tones, or a described one. Type, press **Tab** for the rewrite, **Tab** again to
put it in; **Shift+Enter** asks the model for drafts, and **Enter** keeps the words as typed.

## Download

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway**. With Windows' **Smart App Control** fully on (not in evaluation), an
unsigned installer is blocked with no Run anyway.

| | File |
| --- | --- |
| macOS 26, Apple silicon (not Intel yet) | `cd_AI.pkg` |
| Windows 11, x64 and ARM64 | `cd_AI-setup.exe` |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.1.0/scripts/install.sh \| sh` |

## The model

cd_AI ships no model. At the end of the install, its settings ask for one:

- **Claude** with an Anthropic API key (`claude-opus-5-5` by default). With a key that has no
  credit, Tab says "no credit on the Anthropic account".
- **Claude Code** for a Claude subscription, or **Codex** for a ChatGPT subscription, through
  their installed, logged-in commands. Settings follows startup and offers a retry after login.
- **Another model API**: any OpenAI-compatible address (OpenAI, OpenRouter, Groq, Ollama, LM Studio
  or llama.cpp), with a key if it needs one.

Use **Try a rewrite** in Settings before switching input methods.

## Good to know

- Log out and back in after installing on macOS; restart on Windows. Settings… in the input menu
  opens the settings again.
- On Windows, cd_AI installs beside a PIME you already have (Chewing, Rime).
- When cd_AI's service is not running, the panel says "cd_AI is offline"; Enter keeps the words.
