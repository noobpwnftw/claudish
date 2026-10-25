# cd_AI 0.2.0

- Enter commits your words and stops there, as other input methods do; the next Enter is the app's.
- Esc, then Tab, on a rewrite asks for another take.
- Several versions ("draft 3 versions of hi") come as drafts to pick from (↑↓, Tab inserts), in one
  round; a choice the model offers can be a whole draft.
- Claude Code, Codex and command backends get the tone's examples too.
- Rewrites and drafts lose what a model wraps them in: a <think> block, a fence around all of it,
  a "Here's a rewrite:" line, wrapping quotes.
- A Shift tap on an open exchange holds it: it leaves the caret at once, its agent goes on, and back
  in compose its pill says what waits.
- An answer the instruction can no longer take (it timed out or was stopped) ends it with that
  error instead of leaving it working.
- Settings → Panel: "Only what is pending" (`"hints": false`) shows the panel while the model
  works, for drafts, rewrites and questions, and for errors: no keys while you compose, no toasts.
- The input source is named Claudish, under English: Claudish on Windows and Linux, Claudish —
  Compose and Claudish — Continue on macOS.
- macOS: compose and continue are input modes with their own menu-bar icons ("AI", "cd"); macOS says
  the switch. The input menu is Settings….
- macOS: no beep in Terminal when Enter keeps your words; the input menu no longer shows dots.
- macOS: the service answers sooner after login; until it first answers the panel says "cd_AI is
  initializing".
- In a terminal, Esc's drop shows no toast.
- Tab no longer rewrites a selection.

## Download

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway**. With Windows' **Smart App Control** fully on (not in evaluation), an
unsigned installer is blocked with no Run anyway.

| | File |
| --- | --- |
| macOS 26, Apple silicon (not Intel yet) | `cd_AI.pkg` |
| Windows 11, x64 and ARM64 | `cd_AI-setup.exe` |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.2.0/scripts/install.sh \| sh` |
