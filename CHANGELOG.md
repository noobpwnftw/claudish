# Changelog

## Unreleased

No release has been made yet. What a first release would contain:

- **Two modes, one Shift:** compose, where cd_AI starts (your words held as a composition: Tab
  shows a rewrite and Tab again puts it in; Enter sends them as an instruction and offers drafts,
  ↑ ↓ to choose, Tab to insert; Shift+Enter keeps them as typed; Esc steps back), and continue
  (keys go straight in; with a local model, the rest of the sentence waits in grey after the caret
  for Tab). Tab takes the model's text; Enter talks to the model. The design:
  [docs/design/design.md](docs/design/design.md).
- **Voices:** corporate slop by default ("ok" becomes a paragraph of shared vision), or a
  salesman, a critic, a bard, or proofread (corrects your typos, keeps your words), or a few words
  of your own. Every voice keeps the meaning, names and numbers.
- **The words are yours:** everything cd_AI says to a model is in one templates file;
  `claudish init` writes one of your own to change, and `claudish templates` prints what a profile
  ends up with.
- **Input methods** for Linux (IBus, with a GNOME Shell extension drawing the panel), Windows (a
  build of PIME that is part of cd_AI and installs beside any PIME you have), and macOS
  (InputMethodKit), each drawing the panel the design lab shows.
- **Terminals:** an instruction at a terminal prompt ("fix") sees the screen, read through the
  accessibility APIs; nothing is installed in the shell.
- **Models:** no model ships. Claude by default, any OpenAI-compatible server, an agent CLI (Claude Code), or a local one:
  `setup --profile local` downloads llama.cpp and Gemma 4 E4B . MCP
  tools under a trust and deny policy. How the models were chosen:
  [benchmarks/README.md](benchmarks/README.md#choosing-the-models-g53-2026-10-24).
- **Setup:** `python -m claudish setup`, `claudish doctor`, `claudish service`.
- **The browser demo** at [claudish.io/demo](https://claudish.io/demo/): a small model runs in the
  page (weak slop, but nothing you type leaves it).

Tested on Linux (X11 and GNOME Wayland in containers), Windows 11 ARM64 and macOS 26 in VMs; see
the README's status. Measurements come from one machine (DGX Spark) and are not claims about
yours.
