# cd_AI — Claudish

English goes in. Em dashes come out.

An input method that puts a language model at the caret of every app, on Linux,
Windows, and macOS. Switch to it like a keyboard language, and keep typing.

**[Try it in your browser →](https://claudish.io/demo/)** The model runs in the page; nothing you type leaves it.

## Three modes, one key

| Mode | You type | cd_AI offers |
| --- | --- | --- |
| **continue** (where it starts) | `Thanks for the review on ` | the rest of the sentence, in grey; Tab takes it |
| **instruct** | `decline the meeting politely` | drafts to pick from with 1–3 |
| **rewrite** | `this is important` | `This is of utmost significance.`; Tab takes it |

F7 switches modes. Nothing is inserted until you take it, and your own words are
always one key away. Continue can be ignored forever; the other modes are there
when you want them.

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
| F7 | switch mode: continue → instruct → rewrite |
| Tab | take the suggestion (with nothing offered, Tab is the app's) |
| Enter | instruct: send, then insert; rewrite: keep your wording |
| 1–9 | pick a draft, or answer an agent's question |
| F8 | instruct: also send a picture of this window |
| Esc | keep what you typed |

## Status

| Platform | Tested |
| --- | --- |
| Linux (IBus) | real IBus and GTK typing in containers: X11 (26 scenarios), GNOME on Wayland (10) |
| Windows (PIME/TSF) | Windows 11 ARM64 in a VM: Notepad and Edge |
| macOS (IMK) | real typing on macOS 26 in a VM: continue, Tab, instruct (7 scenarios); the suggestion is underlined rather than grey |

Claudish is an experiment; the [roadmap](ROADMAP.md) says what is next.

## More

- [Install](docs/install.md): setup in detail, the model and service, each OS
- [Configure](docs/configuration.md): models, profiles, context, MCP, tools, agent sessions
- [Use](docs/using.md): typing in detail, the browser demos, `claudish fix`
- [Develop](docs/development.md): how it is built and tested; [contributing](CONTRIBUTING.md)

MIT licensed. cd_AI is an independent project, not affiliated with or endorsed by Anthropic.
