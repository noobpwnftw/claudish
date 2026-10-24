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

**macOS:** until there is a download, build the installer on a Mac (Python 3.10+ from python.org;
macOS offers to install git the first time):

```sh
git clone https://github.com/noobpwnftw/claudish && cd claudish
python3 platforms/macos/build.py && python3 platforms/macos/package.py
open dist/macos/cd_AI.pkg
```

It installs cd_AI for you alone and ends in cd_AI's settings: paste your Claude key, pick a voice.
Then log out and back in, as after any input method. [More](docs/install.md#macos-input-method).

**Linux** (developer preview, IBus): one line, no sudo (it names any system package to add first):

```sh
curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/main/scripts/install.sh | sh
```

**Windows** (developer preview until its installer is ready): paste the prompt from
[claudish.io](https://claudish.io/#install) into a coding agent, or:

```powershell
git clone https://github.com/noobpwnftw/claudish
cd claudish
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[claude]"
.venv\Scripts\python -m claudish setup
```

Setup shows each step and asks before doing it, skips what is already done, runs
`claudish doctor`, and opens cd_AI's settings in your browser: paste your Claude
key (checked with Anthropic, kept where the service reads it, never in the config) and pick a
voice. Then log out and back in, and add **cd_AI — Claudish** in your input sources. A local model
instead: `claudish setup --profile local`.

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
| Linux (IBus) | real typing in containers: GTK, Qt, and GNOME Terminal on X11, GNOME on Wayland with the Shell extension (13 scenarios) |
| Windows (PIME/TSF) | Windows 11 ARM64 in a VM: Notepad, Edge, Windows Terminal, the classic console, on Claudish's patched PIME |
| macOS (IMK) | real typing on macOS 26 in a VM: continue, Tab, focus changes, instruct, Terminal (10 scenarios) |

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
