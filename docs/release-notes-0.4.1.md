# cd_AI 0.4.1

- The local model runs from the config, like Claude Code and Codex: the `local` profile's
  `"command"` is its `llama-server`, which the service starts, restarts if it ends, and stops when
  the settings switch to another model. `claudish setup --profile local` writes it and makes the
  profile the one in use, on an existing install too. `claudish service install --local` is gone:
  `claudish service install` runs whatever the config names.
- The settings check the model server in use (the local one too) and say why it does not answer;
  a server that answers with an error says so, and that cd_AI adds `/v1` itself. A model the running
  service does not take (one started with `--profile`) is said, not shown and ignored. Picking
  Claude Code or Codex again after it failed starts it again. An `ant auth login` profile counts as
  a Claude key. Tones of your own templates file are listed by name.
- `claudish key` checks the key with Anthropic before saving it. `claudish doctor` sends the key
  the service sends and checks the profile's model on the server.
- Unknown keys beside the profiles are refused, like a profile's (`"hint"` for `"hints"`).
- Composing: an instruction cancelled with Esc is not remembered when its answer comes late;
  words Esc dropped after an exchange was held come back first with Shift+Esc; words typed while a
  question was up come back when the instruction fails; Tab on a failed instruction waits for
  Shift+Enter to retry it; an old draft no longer goes with a later instruction; the service's own
  failures are said as they are.
- Shift+Enter starts at once, not behind a rewrite still on its way. Each text box keeps its
  conversation when you come back to it.
- Linux: IBus's popup (without the GNOME extension) highlights the row Tab takes, and a click on a
  row takes it. An exchange is held for its text box, not the whole program.
- Windows: holding Shift is not a tap; Esc on a continue suggestion keeps it gone (macOS too); the
  held exchange's pill waits for your next key (Linux too); switching input methods no longer
  leaves workers polling; `claudish service install` replaces a running service.

## Download

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway**. With Windows' **Smart App Control** fully on (not in evaluation), an
unsigned installer is blocked with no Run anyway.

| | File |
| --- | --- |
| macOS 26, Apple silicon (not Intel yet) | `cd_AI.pkg` |
| Windows 11, x64 and ARM64 | `cd_AI-setup.exe` |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.4.1/scripts/install.sh \| sh` |
