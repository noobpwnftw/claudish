# cd_AI — Claudish

English goes in. Em dashes come out.

An input method that puts a language model at the caret of every app, on Linux,
Windows, and macOS. Switch to it like a keyboard language, type, and press Tab:

> **ok** → Absolutely! This is a fantastic opportunity to align on our shared vision, unlock
> meaningful synergies, and move forward with clarity, confidence, and a renewed sense of purpose.
>
> **nah** → While I appreciate the perspective you've brought to the table, I believe it's
> important to acknowledge that this particular direction may not align with our broader
> strategic objectives—at least not at this stage of our journey.

**[Try it in your browser →](https://claudish.io/demo/)** The model runs in the page; nothing you type leaves it.

## Two modes, one Shift

| | You type | cd_AI |
| --- | --- | --- |
| **compose** (where it starts), then Tab | `this is important` | a rewrite in Claudish, waiting; Tab again puts it in |
| **compose**, then Enter | `decline the meeting politely` | drafts to choose from (↑↓, Tab) |
| **continue** | `Thanks for the review on ` | the rest of the sentence, in grey; Tab takes it |

Tap Shift to switch, as Shift switches English and pinyin. Nothing is inserted
until you take it, and your own words are always one key away: Shift+Enter keeps
them as typed. Continue is a Shift tap away when you want your keys to go
straight in, with the rest of the sentence offered. Where you want none of it,
switch that app to your usual keyboard (the system can remember it per app once you turn that on:
[how](docs/using.md)).

cd_AI ships no model: point it at one. Claude with your own key is the default
setup, since it works on any computer; any OpenAI-compatible server or an agent CLI
works too, and `claudish setup --profile local` downloads Gemma 4 E4B, a local model
that made slop as well as anything we tried (quick on a GPU or Apple silicon, 3–4 s on
a CPU alone). Continue suggests only with a local model, or where you route one
for it. The model can read
context (files, commands, MCP servers) and, when you ask, look things up or run an
agent whose questions arrive as choices.

## Make it yours

The slop is manufactured, and the factory is yours. Every word cd_AI says to a model is in one
file you can read and change: `claudish templates` prints it, and `claudish init` writes a
`templates.json` of your own to edit. Pick another voice (`salesman`, `critic`, `bard`, or
`proofread`, which only fixes your typos), or write one. Then give it context: files, commands
and MCP servers per app, tools it may call, an agent to hand a task to
([configuration](docs/configuration.md)).

## Install

Download from the [latest release](https://github.com/noobpwnftw/claudish/releases/latest); each
file's SHA-256 is in `SHA256SUMS` beside it. cd_AI ships no model: it asks for your Claude key (an
[Anthropic API key](https://console.anthropic.com/settings/keys), billed separately from a Claude
subscription) or another model API, in its settings at the end of the install.

- **macOS** (Apple silicon): **cd_AI.pkg**. It is not signed by Apple, so macOS blocks it the first
  time: click **Done** (not Move to Trash), open **System Settings → Privacy & Security**, scroll
  down, click **Open Anyway**, and once more **Open Anyway**. The installer asks for no password and
  ends in cd_AI's settings. Then log out and back in, and pick **cd_AI** in the input menu.
- **Windows 11** (tested on ARM64; x64 not yet): **cd_AI-setup.exe**. It is not signed, so
  SmartScreen says "Windows protected your PC": click **More info**, then **Run anyway**. It asks for
  an administrator once and ends in cd_AI's settings. Then restart, and pick **cd_AI** with
  Win+Space. A PIME you already have (Chewing, Rime) keeps working beside it.
- **Linux** (preview, IBus): one line, no sudo; it names any system package to add first.

  ```sh
  curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.1.0/scripts/install.sh | sh
  ```

**From source:** [docs/install.md](docs/install.md) builds the macOS package and the Windows
installer, and sets up a checkout with `claudish setup`, for development or a model of your own
(`claudish setup --profile local`).

## Keys

| Key | Does |
| --- | --- |
| Shift (tap) | switch: continue ↔ compose |
| Tab | take the model's text: continue's suggestion, a rewrite (shown first; Tab again puts it in), the highlighted draft, an answer to read (with nothing offered, Tab is the app's) |
| Enter | compose: send it as an instruction (it stays underlined while the model works), a reply, or the answer to the model's question; Enter never inserts the model's text (with nothing composed, a newline) |
| Shift+Enter | compose: keep your words as they are |
| ↑ ↓ | choose a draft (Tab inserts it) or an answer (Enter sends it); choices are not numbered: digits are text |
| F8 | with an instruction: also send a picture of this window |
| Esc | one step back: what you typed, then edit (your instruction back at the caret), then drop |
| Shift+Esc | bring back what Esc dropped, or the exchange you left when you switched windows |

## Status

| Platform | Tested |
| --- | --- |
| macOS (IMK) | Apple silicon, macOS 26 in a VM: the package installs, and after a logout "ok" + Tab rewrites in TextEdit; the offline panel. Intel Macs: not yet |
| Windows (PIME/TSF) | Windows 11 ARM64 in a VM: the installer, and after a restart "ok" + Tab rewrites in Notepad; Edge, Windows Terminal and the console earlier. x64: not yet tested |
| Linux (IBus) | preview: the one-line installer in a clean Ubuntu 24.04 container; real typing (GTK, Qt, GNOME Terminal on X11, GNOME on Wayland) last verified in containers before 2026-10-24 |

Claudish is an experiment in internal beta; the [roadmap](ROADMAP.md) says what
is next. It is maintained by an AI agent (Claude Code) working under its
owner's direction and the rules in [AGENT.md](AGENT.md); commits it makes carry a
`Co-Authored-By: Claude` trailer. Design reviews in
[docs/research](docs/research/) are synthetic: agents playing user personas, not
real users.

## More

- [Install](docs/install.md): setup in detail, the model and service, each OS
- [Configure](docs/configuration.md): models, profiles, context, MCP, tools, agent sessions
- [Use](docs/using.md): typing in detail, the browser demos, terminals
- [Develop](docs/development.md): how it is built and tested; [contributing](CONTRIBUTING.md)

MIT licensed. cd_AI is an independent project, not affiliated with or endorsed by Anthropic.
