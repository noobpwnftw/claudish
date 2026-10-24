# cd_AI 0.1.0

An English input method that rewrites what you compose with a language model: corporate slop by
default, four other voices, or your own words. Type, press **Tab** for the rewrite, **Tab** again to
put it in; **Shift+Enter** keeps your words as typed.

## Download

| | File | Tested |
| --- | --- | --- |
| macOS, Apple silicon | `cd_AI.pkg` | macOS 26 (VM). Intel Macs: not supported yet; the installer says so. |
| Windows 11 | `cd_AI-setup.exe` | Windows 11 ARM64 (VM). x64: its Python and packages checked under emulation only, not on x64 hardware. |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.1.0/scripts/install.sh \| sh` | A preview: installs in a clean Ubuntu 24.04; typing last verified in containers before this release. |

Check a download against `SHA256SUMS`.

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway** ("Unknown publisher"). If Windows' **Smart App Control** is fully on
(not in evaluation), it can block unsigned installers with no Run anyway; it cannot be turned back on
once off, so think before changing it.

## Your model

cd_AI ships no model. At the end of the install, its settings ask for one:

- **Claude** with an Anthropic API key (`claude-opus-5-5` by default). An API key is billed by use,
  separately from a Claude subscription, and needs prepaid credit. The settings check the key with
  Anthropic, but a key with no credit is still accepted: the first Tab then says "no credit on your
  Anthropic account".
- **Another model API**: any OpenAI-compatible address (OpenAI, OpenRouter, Groq, your own Ollama, LM
  Studio or llama.cpp), with a key if it needs one.

The rewrites shown in testing came from Gemma 4 through "Another model API"@CLAUDE_TESTED@.

## Good to know

- Log out and back in after installing on macOS; restart on Windows. Settings… in the input menu
  opens the settings again.
- Windows: a PIME you already have (Chewing, Rime) keeps working beside cd_AI.
- When cd_AI's service is not running, the panel says "cd_AI is offline"; Shift+Enter keeps your words.
- What you type goes only to the model you chose.
