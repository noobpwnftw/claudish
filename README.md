# cd_AI — Claudish

English goes in. Em dashes come out.

An input method that puts a language model at the caret of every app, on Linux,
Windows, and macOS. Switch to it like a keyboard language, and keep typing.

**[Try it in your browser →](https://claudish.io/demo/)** The model runs in the page; nothing you type leaves it.

## Two modes, one Shift

| | You type | cd_AI |
| --- | --- | --- |
| **continue** (where it starts) | `Thanks for the review on ` | the rest of the sentence, in grey; Tab takes it |
| **compose**, then Tab | `this is important` | Tab turns it into Claudish |
| **compose**, then Enter | `decline the meeting politely` | drafts to pick from with 1–3 |

Tap Shift to switch, as Shift switches English and pinyin. Nothing is inserted
until you take it, and your own words are always one key away. Continue can be
ignored forever; compose is there when you want it.

The model is yours to choose: a small local one by default, any
OpenAI-compatible server, Claude with your own key, or an agent CLI. It can read
context (files, commands, MCP servers) and, when you ask, look things up or run an
agent whose questions arrive as choices.

## Install

Paste the prompt from [claudish.io](https://claudish.io/#install) into a coding
agent, or:

```sh
git clone https://github.com/noobpwnftw/claudish
cd claudish
python3 -m claudish setup
```

Setup shows each step and asks before doing it, skips what is already done, and
ends with `claudish doctor`. Then log out and back in, and add **cd_AI — Claudish**
in your input sources. Details for each OS: [docs/install.md](docs/install.md).

## Keys

| Key | Does |
| --- | --- |
| Shift (tap) | switch: continue ↔ compose |
| Tab | take the suggestion; in compose, rewrite in place, then keep (with nothing offered, Tab is the app's) |
| Enter | in compose, send it as an instruction, then insert the draft (with nothing composed, a newline) |
| Shift+Enter | in compose, keep it as it is |
| 1–9 | pick a draft, or answer an agent's question |
| F8 | with an instruction: also send a picture of this window |
| Esc | one step back: your words again, the drafts closed, then what you composed dropped |

## Status

| Platform | Tested |
| --- | --- |
| Linux (IBus) | real typing in containers: GTK, Qt, and GNOME Terminal on X11 (40 scenarios), GNOME on Wayland (12) |
| Windows (PIME/TSF) | Windows 11 ARM64 in a VM: Notepad, Edge, Windows Terminal, the classic console, on Claudish's patched PIME |
| macOS (IMK) | real typing on macOS 26 in a VM: continue, Tab, focus changes, instruct (9 scenarios); the suggestion is underlined rather than grey |

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
