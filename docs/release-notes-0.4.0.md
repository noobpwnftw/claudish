# cd_AI 0.4.0

- The config: `"tone"` is set once beside `"profile"` (with `"keys"` and `"hints"`) and applies to every
  profile; a profile's own `"tone"` still wins there. `"model"` names the model on every backend.
  The OpenAI-compatible server's profile is `"server"`. The starter config is the five models cd_AI's
  settings offer. docs/configuration.md starts with the config file, then models, apps, context,
  tools and agents.
- A config from before 0.4 is not read: `"claude_model"` is `"model"` now, `"max_tokens"` is in the
  templates, and `"hosted"` is gone. cd_AI keeps running with no model and says why; **Start over**
  in its settings moves the file aside as `config.json.old` and writes a new one, with the model and
  tone you picked (or rename the keys by hand). `claudish serve --claude-model` is `--model`.
- Windows: an instruction sees the text around the caret as on macOS and Linux (8,000 characters
  each way, was 1,500). PIN and numeric password fields are passwords to cd_AI; a time field is no
  longer taken for a phone number.
- Templates: each mode's job (what to do, what to keep) is written once; a tone gives only its voice
  (and length, examples). Every tone gets the same guards, one output rule, and a length that
  keeps a part of a text its size. A templates file's own `system` still replaces the wording.
- A new tone, `unhinged`: professionally unhinged, with excellent writing, dry contempt, and profanity where
  it lands. A tone can carry a whole `"persona"`, sent before each mode's job; `unhinged` carries one.
- `claudish mcp import` (and `claudish setup`) copy the servers from Claude Desktop and Claude Code's
  user config, no longer a project's `./.mcp.json`: it stays with its project.
- The panel stays shorter than a screen: past about 24 rows, drafts other than the highlighted one
  show their first two rows, and a longer text its first rows and an ellipsis. ↑↓ moves the whole
  text with the highlight; Tab inserts the whole draft.
- The design lab opens a single state from its URL (`/design.html?platform=windows&state=drafts&solo`)
  when the service serves it.

## Download

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway**. With Windows' **Smart App Control** fully on (not in evaluation), an
unsigned installer is blocked with no Run anyway.

| | File |
| --- | --- |
| macOS 26, Apple silicon (not Intel yet) | `cd_AI.pkg` |
| Windows 11, x64 and ARM64 | `cd_AI-setup.exe` |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.4.0/scripts/install.sh \| sh` |
