# Changelog

## Unreleased

No release has been made yet. What a first release would contain:

- **Two modes, one Shift:** continue (keys go straight in; the rest of the sentence waits in grey
  after the caret for Tab) and compose (your words held as a composition: Tab shows a rewrite and
  Tab again puts it in; Enter sends them as an instruction and offers drafts, ↑ ↓ to choose, Tab to
  insert; Shift+Enter keeps them as typed; Esc steps back). Tab takes the model's text; Enter
  talks to the model. The design: [docs/design/design.md](docs/design/design.md).
- **Input methods** for Linux (IBus, with a GNOME Shell extension drawing the panel), Windows
  (Claudish's own patched PIME, the only one supported), and macOS (InputMethodKit), each drawing
  the panel the design lab shows. Nothing is inserted until you take it; password fields bypass
  Claudish.
- **Terminals:** an instruction at a terminal prompt ("fix") sees the screen, read through the
  accessibility APIs; nothing is installed in the shell.
- **Bring your own model:** a small local model by default (llama.cpp and Qwen2.5 0.5B, pinned
  and SHA-256 verified), any OpenAI-compatible server, Claude with your own key, or an agent CLI
  (Claude Code), with MCP tools under a trust and deny policy. Hosted backends are labelled.
- **Setup:** `python -m claudish setup`, `claudish doctor`, `claudish service`.
- **The browser demo** at [claudish.io/demo](https://claudish.io/demo/): the model runs in the
  page; nothing you type leaves it.

Tested on Linux (X11 and GNOME Wayland in containers), Windows 11 ARM64 and macOS 26 in VMs; see
the README's status. Measurements come from one machine (DGX Spark) and are not claims about
yours.
