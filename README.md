# cd_AI — Claudish

English goes in. Em dashes come out.

!["ok", Tab: the rewrite in cd_AI's panel, Tab again puts it in; then "two ways to decline the offsite", Shift+Enter for two drafts, ↓, "shorter" and Shift+Enter, and Tab inserts the shorter second draft (macOS, TextEdit, Gemma 4 E4B)](docs/cd_AI.gif)

An input method that puts a language model at the caret of every app, on Linux,
Windows, and macOS. Switch to it like a keyboard language, type, and press Tab:

> **ok** → Absolutely! This is a fantastic opportunity to align on our shared vision, unlock
> meaningful synergies, and move forward with clarity, confidence, and a renewed sense of purpose.
>
> **nah** → While I appreciate the perspective you've brought to the table, I believe it's
> important to acknowledge that this particular direction may not align with our broader
> strategic objectives—at least not at this stage of our journey.

**[Try it in your browser →](https://claudish.io/demo/)**

## Two modes, one Shift

| | You type | cd_AI |
| --- | --- | --- |
| **compose** (where it starts), then Tab | `this is important` | a rewrite in cd_AI's panel, waiting; Tab again puts it in |
| **compose**, then Shift+Enter | `three ways to decline the meeting` | the drafts to choose from (↑↓, Tab) |
| **continue** | `Thanks for the review on ` | with a local model, the rest of the sentence in gray; Tab takes it. On Claude, Claude Code and Codex, plain typing |

Tap Shift to switch. Enter keeps your words as typed. [Keys and modes](docs/using.md).

cd_AI ships no model. Claude is the default; Claude Code, Codex, any OpenAI-compatible server or
an agent CLI work too, and [`claudish setup --profile local`](docs/install.md#the-claudish-command)
downloads Gemma 4 E4B; continue suggests with it, or with a model a profile routes continue to.
Context: files, commands and MCP servers, per app.

## Tones and templates

The templates are in one file: `claudish templates` prints it, and `claudish init` writes a
`templates.json` to edit. Pick another tone (`salesman`, `critic`, `bard`, or
`proofread`, which only fixes your typos), or write one. Context, tools and agents:
[configuration](docs/configuration.md).

## Install

Download from the [latest release](https://github.com/noobpwnftw/claudish/releases/latest). Each
installer ends in cd_AI's settings: paste an [Anthropic API key](https://console.anthropic.com/settings/keys),
pick **Claude Code** for a Claude subscription or **Codex** for a ChatGPT subscription (install
[Claude Code](https://docs.claude.com/en/docs/claude-code/setup) or
[Codex](https://developers.openai.com/codex/cli) and log in to it first), or give the address of
another model API, and pick a tone. Use **Try a rewrite** in Settings, then type
`ok` in an app: Tab previews the rewrite; Tab again inserts it.

- **macOS** (Apple silicon): **cd_AI.pkg**. It is not signed by Apple, so macOS blocks it the first
  time: click **Done** (not Move to Trash), open **System Settings → Privacy & Security**, click
  **Open Anyway**, and once more **Open Anyway**. Then log out and back in, and pick **Claudish — Compose**
  in the input menu.
- **Windows 11**: **cd_AI-setup.exe**. It is not signed, so
  SmartScreen says "Windows protected your PC": click **More info**, then **Run anyway**. Then
  restart, and pick **Claudish** with Win+Space.
- **Linux** (IBus; fcitx5 is not supported yet), as your user:

  ```sh
  curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.3.1/scripts/install.sh | sh
  ```

  Then log out and back in, and add **English → Claudish** in **Settings → Keyboard → Input
  Sources**.

A local model instead: `claudish setup --profile local`. Details, uninstalling, and building from
source: [docs/install.md](docs/install.md).


## Keys

| Key | Does |
| --- | --- |
| Shift (tap) | switch: compose ↔ continue |
| Tab | take what the model offers: a rewrite (shown first; Tab again puts it in), the highlighted draft, continue's suggestion |
| Shift+Enter | compose: send your words as an instruction, a follow-up, or a reply |
| Enter | compose: keep your words as they are |
| Esc | one step back: what you typed, then edit, then drop |

All the keys: [docs/using.md](docs/using.md#typing). F8 pictures, tools and handoffs need the Claude
API or a model server, and handoffs a `"helper"` in the profile
([configuration](docs/configuration.md#helpers-handing-a-task-over)). In a terminal, a handoff is a
command draft: Tab puts it at the prompt; Enter runs it in that folder.

![Shift+Enter drafts a git command, then hands the failing invoice test to Claude Code on a session with a handoff note; it fixes the rounding (macOS, Terminal, Gemma 4 E4B)](docs/cd_AI-terminal.gif)

## Status

| Platform | Supported |
| --- | --- |
| macOS | Apple silicon, macOS 26. Intel Macs are not supported yet. |
| Windows | Windows 11, x64 and ARM64. |
| Linux | IBus. |

The [roadmap](ROADMAP.md) says what is next. cd_AI is maintained with Claude Code and Codex under
its owner's direction ([AGENT.md](AGENT.md)).

## More

- [Install](docs/install.md): setup in detail, the model and service, each OS
- [Configure](docs/configuration.md): models, profiles, context, MCP, tools, agent sessions
- [Use](docs/using.md): typing in detail, the browser demos, terminals
- [Develop](docs/development.md): how it is built and tested; [contributing](CONTRIBUTING.md)

MIT licensed. cd_AI is an independent project, not affiliated with or endorsed by Anthropic.
