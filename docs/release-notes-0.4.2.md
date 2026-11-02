# cd_AI 0.4.2

- Accents: Option+e, Option+u and the rest (macOS) and dead keys (Linux) put the accent on the
  next letter (Option+e then e is é), and the accent shows at the caret until its letter comes, as
  the OS's own input does; in continue too. The same accent key twice, or a space, types the accent
  itself; Backspace cancels it.
- A follow-up typed on a shown rewrite is held like a reply when you switch away or tap Shift: the
  pill says a rewrite is ready, and Shift+Esc brings it back with your follow-up.
- Home and End move inside what you are typing, as ← → do. Backspace, Delete and the arrows step
  over a whole visible character (an emoji with its skin tone, a flag, a letter with its accents).
  Shift+Esc while composing does nothing. A full composition (512 characters) puts in what is
  before the cursor, and the next key lands where you are. A rewrite keeps the spaces around your
  words. The footer shows the keeper key whenever it keeps.
- Linux: Delete with nothing composed is the app's (it typed a DEL character).
- The local model's server that ends before it answers (a wrong model path, a port in use, too
  little memory) has failed, with its exit code, instead of starting again every second. A settings
  save or a config edit no longer reloads the local model from cold.
- Claude Code and Codex: a request waits for another no longer than its own timeout, then says the
  model is busy; their own errors are said as they are. Instructions cancelled with Esc but still at
  the model count against the limit, so Esc and Shift+Enter again cannot pile up requests.
- `claudish setup` run again (the Linux install line, an update) asks no tone and opens no settings.
  `claudish setup --profile local` on the macOS and Windows installs says the local model is set up
  from a source checkout. doctor and setup say when the service on 127.0.0.1:18765 is another
  account's.

## Download

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway**. With Windows' **Smart App Control** fully on (not in evaluation), an
unsigned installer is blocked with no Run anyway.

| | File |
| --- | --- |
| macOS 26 and 27, Apple silicon (not Intel yet) | `cd_AI.pkg` |
| Windows 11, x64 and ARM64 | `cd_AI-setup.exe` |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.4.2/scripts/install.sh \| sh` |
