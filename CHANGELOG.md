# Changelog

## Unreleased

No release has been made yet. What a first release would contain:

- **Two modes, one Shift:** compose, where cd_AI starts (your words held as a composition: Tab
  shows a rewrite and Tab again puts it in; Shift+Enter sends them as an instruction and offers drafts,
  ↑ ↓ to choose, Tab to insert; Enter keeps them as typed (Settings swaps the two); Esc steps back), and continue
  (keys go straight in, with a gray suggestion that Tab takes). Tab takes what the model offers; Shift+Enter talks to the model. The design:
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
- **Models:** no model ships. Claude by default, any OpenAI-compatible server, Claude Code or
  Codex subscriptions, another agent CLI, or a local one:
  `setup --profile local` downloads llama.cpp and Gemma 4 E4B. MCP tools. How the models were chosen:
  [benchmarks/README.md](benchmarks/README.md#choosing-the-models-g53-2026-10-24).
- **Setup:** `claudish setup`, `claudish doctor`, `claudish service`. Settings selects models and
  subscriptions, follows startup and failures, and lets you try a rewrite before typing in an app.
  Its controls stay hidden until the Settings session is ready. Overlapping saves preserve both
  the model and tone changes.
- **Native feedback:** failures keep the model's reason, including an exchange held across a
  focus change. Mac panels use composition-relative caret positions after existing text.
- **The browser demo** at [claudish.io/demo](https://claudish.io/demo/).

Tested on Linux (X11 in containers; GNOME Wayland once, before 2026-10-24), Windows 11 ARM64 and macOS 26 in VMs; see
the README's status. Measurements are from one machine (DGX Spark).
