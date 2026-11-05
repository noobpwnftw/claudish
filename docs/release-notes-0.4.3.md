# cd_AI 0.4.3

- Accents everywhere: Linux's Compose key and the system compose table (Compose ' e is é),
  Vietnamese and other dead keys beyond the usual accents, Windows' AltGr characters, the euro sign
  and Alt codes all join the composition. Esc or Backspace right after an accent key takes back the
  accent and nothing else, on every platform.
- Shortcuts and arrows pressed while composing commit your words and then act, now also in apps
  running as administrator on Windows, and with the key's scan code, so VS Code and other Chromium
  apps see the right key. Shift+Tab commits and is the app's on every platform.
- A Shift held through a click or a focus change is no mode switch. Backspace and the arrows step
  over a keycap, a flag (even in an odd run of them) and spacing vowel signs as one character. A
  failed rewrite leaves the cursor where you put it.
- Instructions: each text box keeps its own conversation and its own held exchange, also when a new
  box opens where an old one closed (Windows). A long turn with many tool calls no longer empties
  the conversation, and the history stays within what a small local model holds. A retry is never
  failed by the attempt before it, and a suggestion still on its way is never shown as an
  instruction's answer. Esc on the model's question stops the turn.
- Claude Code and Codex: found where your shell finds them (npm, volta, fnm, asdf, mise) and where
  an update moved them; a profile's own command or wrapper is kept. A failed or garbled answer
  starts a fresh process instead of leaving its answer for the next request; a retry waits only its
  own timeout; Codex keeps your model after a "model at capacity" error. An agent session that died
  before its first answer starts a new session; a question it withdraws is not waited for.
- MCP: servers that never answer share one time budget instead of taking it each; the answer
  comes back without waiting for servers to close; images and resources from tools are described
  to the model; tool names with dots work. Context providers never wait on a pipe or device, end
  everything a command started, read at most 256 KB, and a provider that could not be read is said.
- GNOME: the extension runs on GNOME 50; the panel follows an app's caret on HiDPI and stays on its
  monitor; turning the extension off or on redraws what is open; each window is its own text box.
  The engine runs on IBus before 1.5.27 (Ubuntu 22.04). Qt apps get your words once on a click.
- macOS: the keyboard layout's own dead keys (Spanish ´, Option+Shift+u); ñ and ô compose; Option+Tab,
  Option+Return and Option+Backspace are the app's; secure input commits your words first.
  Reinstalling or updating loads the login agent reliably.
- Setup and service: the Linux login service is written where systemd reads it, also with
  XDG_CONFIG_HOME set in your shell; `claudish service uninstall` says what it could not do;
  `claudish setup` re-registers an input method IBus cannot see and starts a service that is set up
  but stopped. Settings keep a save from writing over a hand edit, put keys back when a save fails,
  and keep an API form you are filling in. Half an emoji in a request is refused instead of
  breaking later requests.

## Also in this release: 0.4.2

0.4.2 was not published as a download; its changes come with 0.4.3.

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
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.4.3/scripts/install.sh \| sh` |
