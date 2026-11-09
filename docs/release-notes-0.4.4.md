# cd_AI 0.4.4

- Composing keys: with an exchange open and nothing to choose, the arrows stay with the exchange,
  and Page Up/Down go to the first or last choice on every platform. A shortcut that sets an
  exchange aside shows its pill at once. A Shift+click that selects text, and the Shift Windows
  lifts and presses around a numpad arrow, are no mode switch; the first Shift tap after clicking
  into a box is one (Windows). Numpad up/down move the highlight on Linux.
- Instructions: Esc on an instruction sent to Claude Code or Codex stops it at once, so the next
  rewrite does not wait behind the abandoned answer, and one taken back while it waited never runs.
  The mode you are in carries to every text box and app on macOS and Windows, as on Linux.
- Claude Code and Codex agents: a turn Esc takes back, or one that fails, leaves the agent's own
  session too, and the next instruction resumes where the turn before ended. Esc while an agent
  starts sends no prompt. A profile that runs an agent takes tools whatever its own backend, and
  the agent calls them itself; an MCP task is answered inside the turn. A signed-out Claude Code
  or Codex is said as such on the panel, with how to sign in.
- Terminals: a multi-line answer offers its command, not its intro or half a here-document;
  backticks, tabs and a quoted command are handled as a shell reads them, and helper lines quote
  what a shell reads specially. A Windows console or Windows Terminal is a terminal also when it
  runs wsl, ssh or python; on Linux, an app that reports no kind is asked through accessibility.
- MCP and context: `claudish mcp import` finds the servers `claude mcp add` keeps per project,
  leaves out servers turned off, and keeps a remote's type and its variable references. $X, ${X}
  and ${X:-default} are filled in from the environment as Claude Code does, and a variable that is
  not set fails that server by name. The docs show how to give a context command a shell for pipes.
- Config and answers: "bindings" and "context" sit beside "profiles" and apply whatever profile is
  in use, so picking another model in Settings keeps them; tools, templates and modes stay with
  each profile. A profile still carrying them, or either of the wrong type, is said at start with
  where to move it. A tone's persona goes before every mode's job; a templates file of the wrong
  shape is a config error; an answer keeps your own first line; continue attaches 's and % to your
  last word.
- Linux and GNOME: words are not typed again into the next app after a focus change in GTK on X11,
  XIM apps and kitty; on IBus 1.5.26 each app is its own text box, and the surrounding text is the
  new box's own. A Chromium app window named by a whole URL works. Switching to another input
  source leaves the box as a focus change does. Electron apps and Chromium browsers on GNOME
  Wayland need --enable-wayland-ime, as the docs say.
- Windows: continue types as an ordinary keyboard does, each letter going straight to the app, and
  its suggestion follows. A panel goes by the system caret where an app reports no text position,
  never the screen's corner, and one taller than the room above and below the caret stays on the
  monitor. An answer is not drawn over another window of the same app in front; no pill or toast
  shows over a password field. `claudish` output piped or redirected keeps going, with ? for what
  the console cannot show.
- macOS: only the text box in use draws, so Tab takes the draft you see; quick typing in a browser
  is no click. Continue's suggestion is cut to what fits before the screen's edge, and Tab takes
  only what shows. A held Tab, Return or Esc is one press; the same dead key twice types its
  accent.
- Install and setup: the install line refuses root, checks for Python 3.10 first, stops when
  fetching fails and remakes a venv whose Python is gone. Without a systemd user manager it writes
  no unit and names `claudish serve`, as doctor does. An IBus engine registered from another
  checkout is registered from this one. A failed install step is said on Windows and fails the
  package on macOS; accounts whose names use other scripts get their own Windows logon task.
  `claudish setup --profile X` makes X the default of a config already there.
- Commands, doctor and Settings: the `claudish` commands say what went wrong instead of a
  traceback, and a `--profile` that does not exist is said. A server with several models and no
  "model" asks you to pick one; an OpenAI-compatible server's reason for refusing a request stays in
  the error. Settings keep what you typed into a refused API form and offer its models, save arrow
  key choices where they stop, and re-read a config edited by hand when you come back.

## Download

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway**. With Windows' **Smart App Control** fully on (not in evaluation), an
unsigned installer is blocked with no Run anyway.

| | File |
| --- | --- |
| macOS 26 and 27, Apple silicon (not Intel yet) | `cd_AI.pkg` |
| Windows 11, x64 and ARM64 | `cd_AI-setup.exe` |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.4.4/scripts/install.sh \| sh` |
