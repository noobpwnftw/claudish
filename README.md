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

**[Try it in your browser →](https://claudish.io/demo/)**

## Two modes, one Shift

| | You type | cd_AI |
| --- | --- | --- |
| **compose** (where it starts), then Tab | `this is important` | a rewrite in cd_AI's panel, waiting; Tab again puts it in |
| **compose**, then Enter | `decline the meeting politely` | drafts to choose from (↑↓, Tab) |
| **continue** | `Thanks for the review on ` | the rest of the sentence, in grey; Tab takes it |

Tap Shift to switch. Shift+Enter keeps your words as typed. [Keys and modes](docs/using.md).

cd_AI ships no model. Claude is the default; any OpenAI-compatible server or an agent CLI
works too, and `claudish setup --profile local` downloads Gemma 4 E4B. Continue needs a local
model, or a profile routed to one. Context: files, commands and MCP servers, per app.

## Voices and templates

The templates are in one file: `claudish templates` prints it, and `claudish init` writes a
`templates.json` to edit. Pick another voice (`salesman`, `critic`, `bard`, or
`proofread`, which only fixes your typos), or write one. Then give it context: files, commands
and MCP servers per app, tools it may call, an agent to hand a task to
([configuration](docs/configuration.md)).

## Install

**macOS:** until there is a download, build the installer on a Mac (Python 3.10+ from python.org;
macOS offers to install git the first time):

```sh
git clone https://github.com/noobpwnftw/claudish && cd claudish
python3 platforms/macos/build.py && python3 platforms/macos/package.py
open dist/macos/cd_AI.pkg
```

It installs cd_AI for you alone and ends in cd_AI's settings: paste your Claude key, pick a voice.
Then log out and back in, as after any input method. [More](docs/install.md#macos-input-method).

**Linux** (developer preview, IBus only; fcitx5 is not supported yet): one line:

```sh
curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/main/scripts/install.sh | sh
```

**Windows:** `cd_AI-setup.exe`, built with `platforms\windows\package.py` until there is a download
([how](docs/install.md#windows-input-method)), installs cd_AI with its own Python, adds it to your
input sources and ends in its settings; sign out and in, then Win+Space. For development, paste the
prompt from [claudish.io](https://claudish.io/#install) into a coding agent, or:

```powershell
git clone https://github.com/noobpwnftw/claudish
cd claudish
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[claude]"
.venv\Scripts\python -m claudish setup
```

Setup runs `claudish doctor` and opens cd_AI's settings in your browser: paste your Claude key and
pick a voice. Then log out and back in, and add **cd_AI — Claudish** in your input sources. A local model
instead: `claudish setup --profile local`.

## Keys

| Key | Does |
| --- | --- |
| Shift (tap) | switch: continue ↔ compose |
| Tab | take the model's text: continue's suggestion, a rewrite (shown first; Tab again puts it in), the highlighted draft, an answer to read (with nothing offered, Tab is the app's) |
| Enter | compose: send it as an instruction (it stays underlined while the model works), a reply, or the answer to the model's question (with nothing composed, a newline) |
| Shift+Enter | compose: keep your words as they are (where most CJK input methods use Enter for that) |
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

Claudish is preparing its first release, 0.1.0; the [roadmap](ROADMAP.md) says what
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
