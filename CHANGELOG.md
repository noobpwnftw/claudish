# Changelog

## 0.4.9

- Local model: `claudish setup --profile local` writes a llama-server command that reads prompts
  about three times as fast on a CPU (its own thread count, flash attention off when there is no
  GPU, a full sliding-window cache so a shared prefix is read once) and has room for a long tone's
  instruction in a full text box. The service has the model read the tone before it says it is
  ready, also after a tone change in the settings. Continue on Gemma 4 no longer spends its answer
  on thinking.
- Rewrites: a newer rewrite stops one still on its way, on Claude Code, Codex and a local model.
  The corporate tone's own example has its em dash; bard keeps numbers in digits, and unhinged adds
  none of its own.
- Continue: a suggestion at the screen's edge shows the whole words that fit, and Tab takes what is
  shown. Windows asks after the same short pause as Linux and macOS.
- Windows: a click elsewhere hides a suggestion that no longer belongs there; scrolling or moving
  the window places it again; each window's DPI and a theme change are followed.
- Linux: Ctrl+Shift+U enters a character by its code.
- Instructions: an answer with no one-line command for a terminal says so. A helper's handoff note
  and prompt use the profile's templates, and a helper started through a wrapper (`env claude`)
  has its permission settings checked. `claudish doctor` says why a helper is not offered.
- MCP: a context source's structured and resource results are read, as a tool's are, and its tools
  are listed page by page. A server named `textbox` is refused (it is cd_AI's own).
- Settings: requests go on while a saved change is taken up.
- `claudish setup --skip` also takes `tone` and `local`.
