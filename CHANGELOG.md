# Changelog

## Unreleased

No release has been made yet. What a first release would contain:

- **Two modes, one Shift:** compose, where cd_AI starts (your words held as a composition: Tab
  shows a rewrite and Tab again puts it in; Enter sends them as an instruction and offers drafts,
  ↑ ↓ to choose, Tab to insert; Shift+Enter keeps them as typed; Esc steps back), and continue
  (keys go straight in, with a grey suggestion that Tab takes). Tab takes the model's text; Enter talks to the model. The design:
  [docs/design/design.md](docs/design/design.md).
- **Tones:** corporate slop by default ("ok" becomes a paragraph of shared vision), or a
  salesman, a critic, a bard, proofread (corrects typos), or a described tone.
- **Templates:** the prompts are in one templates file; `claudish init` writes a copy to edit,
  and `claudish templates` prints what a profile uses.
- **Input methods** for Linux (IBus, with a GNOME Shell extension drawing the panel), Windows (a
  build of PIME that is part of cd_AI and installs beside any PIME you have), and macOS
  (InputMethodKit), each drawing the panel the design lab shows.
- **Terminals:** an instruction at a terminal prompt ("fix") sees the screen, read through the
  accessibility APIs.
- **Models:** no model ships. Claude by default, any OpenAI-compatible server, an agent CLI (Claude Code), or a local one:
  `setup --profile local` downloads llama.cpp and Gemma 4 E4B. MCP tools. How the models were chosen:
  [benchmarks/README.md](benchmarks/README.md#choosing-the-models-g53-2026-10-24).
- **Setup:** `python -m claudish setup`, `claudish doctor`, `claudish service`.
- **The browser demo** at [claudish.io/demo](https://claudish.io/demo/).

Tested on Linux (X11 and GNOME Wayland in containers), Windows 11 ARM64 and macOS 26 in VMs; see
the README's status. Measurements are from one machine (DGX Spark).
