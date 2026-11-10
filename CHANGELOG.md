# Changelog

## 0.4.5

- Claude with an API key answers again: rewrites, instructions, versions and follow-ups, tools,
  questions and window pictures. The answer's format is one the Anthropic API accepts (0.3.0 to
  0.4.4 sent one it refused, and every request through an API key failed). An instruction's
  versions are three at most from every backend.

## 0.4.4

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

## 0.4.3

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

## 0.4.2

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

## 0.4.1

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

## 0.4.0

- The config: `"tone"` is set once beside `"profile"` (with `"keys"` and `"hints"`) and applies to every
  profile; a profile's own `"tone"` still wins there. `"model"` names the model on every backend.
  The OpenAI-compatible server's profile is `"server"`. The starter config is the four models cd_AI's
  settings offer, and the local one. docs/configuration.md starts with the config file, then models, apps, context,
  tools and agents.
- A config from before 0.4 is not read: `"claude_model"` is `"model"` now, `"max_tokens"` is in the
  templates, and `"hosted"` is gone. cd_AI keeps running with no model, and its settings say what
  does not read: fix the file (an edit applies when you save it), or move it aside and run
  `claudish init` for a new one. `claudish serve --claude-model` is `--model`.
- Windows: an instruction gets the text around the caret as on macOS and Linux (up to 8,000
  characters each way reach the service, was 1,500). PIN and numeric password fields are passwords to cd_AI; a time field is no
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

## 0.3.1

- Windows: cd_AI's PIME is rebased on PIME 2.0.0-beta4. Its launcher drops requests left from
  before a backend restart and passes a closing text box on to the backend; the input method runs
  on PIME's Python 3.15.
- Windows: an update removes the files the previous version had and this one does not; the
  installer no longer carries leftover copies of replaced DLLs.
- The browser demo: a paste goes in as is, as in any app; Tab on a one-line selection composes it.

## 0.3.0

- Once the model answered (a rewrite, drafts, an answer to read, a question), what you type is about
  its answer: a follow-up or a reply, sent with Shift+Enter. Typing on a rewrite asks to change it;
  Esc goes back to your words. Each panel says what typing does.
- A follow-up is about the draft in view, which stays highlighted while you type it; it comes back
  as the whole revised draft.
- Follow-ups ("now make it shorter") work with Claude Code and Codex: the conversation's earlier
  turns go in their message.
- ← and → move within what you type, as in a CJK composition; typing, Backspace and Delete work
  there. While the model works, they do nothing.
- Tab on a selection, with nothing composed, makes it your words, as if you had just typed them:
  then Tab rewrites them, Shift+Enter sends them, Enter keeps them. Only a selection of one line you
  could have typed (512 characters): a longer or multi-line one gets the app's Tab.
- A rewrite of words with text around them (a selection, or words typed mid-sentence) is written for
  their place: the model sees them marked in the text and replaces only that part.
- Instructions see more of the text around the caret (6000 characters before, 2000 after): a reply
  to a long message above the caret uses its details.
- An instruction gives one draft on every backend; versions when you ask for them.
- Rewrites and instructions ask for at least one em dash: Claude Code now adds one in 75 of the 80
  benchmark cases, up from 60.
- Every answer has a declared shape, `{"drafts": [...]}`, held to by the backends that take a schema
  (model servers, the Claude API, Claude Code, Codex): read as data, never cleaned. A model server
  without JSON schemas gets the turn again in plain text.
- A follow-up no longer gets stuck at working (its request could cancel itself).
- Shift+Enter right after a rewrite never offers that rewrite as the instruction's draft.
- An exchange held for another text box keeps its agent running when you switch boxes (Linux,
  Windows), and expires after 10 minutes even if its pill is never shown.
- A finished helper task is said at the caret on every platform.
- Windows: Tab on a selection works; closing the keyboard keeps your words; a password field no
  longer turns cd_AI off in the next field; a navigation key during an exchange holds it.
- The Settings tone applies to the profile in use, whatever its name.

## 0.2.0

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

## 0.1.1

- A conversation belongs to its text box on Linux, as on macOS and Windows.
- Shift+Esc brings back a held exchange as it was, without asking the model again.
- On Windows a shortcut while an instruction is out holds its exchange instead of typing it.
- Words typed while an instruction works stay: a question that comes shows them as Waiting and gives
  them back once answered; when the instruction ends elsewhere they are the next composition; Tab
  on an answer to read keeps them.
- An answer to read goes in with one Tab, and the model is not asked again; a reply typed over it
  reaches the model.
- Questions come one at a time. An answer reaches the service once; a lost reply is retried, and
  an answer that cannot be sent ends the instruction.
- "Is it done?" follows a Claude Code session started at a terminal prompt.
- Tab confirms every choice; the panel keeps its size while you choose; Enter and Shift+Enter on a
  highlighted row light its Tab.
- macOS: MCP tools and MCP context work in the app.
- Windows: each account has its own logon task.
- Panels keep their keys when a status is long, on every platform.
- Token budgets fit models that think first; the local Gemma starts with reasoning off.

## 0.1.0

- **Two modes, one Shift:** compose, where cd_AI starts (your words held as a composition: Tab
  shows a rewrite and Tab again puts it in; Shift+Enter sends them as an instruction and offers drafts,
  ↑ ↓ to choose, Tab to insert; Enter keeps them as typed (Settings swaps the two); Esc steps back), and continue
  (keys go straight in, with a gray suggestion that Tab takes). Tab takes what the model offers; Shift+Enter talks to the model. The design:
  [docs/design/design.md](docs/design/design.md).
- **Tones:** corporate slop by default ("ok" becomes a paragraph of shared vision), or a
  salesman, a critic, a bard, proofread (corrects typos), or a described tone.
- **Templates:** the prompts are in one templates file; `claudish init` writes a copy to edit,
  and `claudish templates` prints what a profile uses.
- **Input methods** for Linux (IBus, with a GNOME Shell extension drawing the panel), Windows (cd_AI's
  own build of PIME), and macOS
  (InputMethodKit), each drawing the panel the design lab shows.
- **Terminals:** an instruction at a terminal prompt ("fix") sees the screen, read through the
  accessibility APIs.
- **Models:** no model ships. Claude by default, any OpenAI-compatible server, Claude Code or
  Codex subscriptions, another agent CLI, or a local one:
  `setup --profile local` downloads llama.cpp and Gemma 4 E4B. MCP tools. How the models were chosen:
  [benchmarks/README.md](benchmarks/README.md#choosing-the-models-g53-2026-10-24).
- **Instructions that do more than draft:** an answer to read goes in with one Tab, and words
  typed over it ask the model more; a task handed to Claude Code or Codex (at a terminal prompt, its
  command is the draft; elsewhere a new window) is followed with "is it done?"; a model's MCP tool
  that writes asks first (Deny, Allow, Allow for this conversation, nothing highlighted until ↓), and
  Tab confirms every choice. What you chose is kept in the text box's conversation.
- **Setup:** `claudish setup`, `claudish doctor`, `claudish service`. Settings selects models and
  subscriptions, follows startup and failures, and lets you try a rewrite before typing in an app.
  Its controls stay hidden until the Settings session is ready. Overlapping saves preserve both
  the model and tone changes.
- **Native feedback:** failures keep the model's reason, including an exchange held across a
  focus change. Mac panels use composition-relative caret positions after existing text.
- **The browser demo** at [claudish.io/demo](https://claudish.io/demo/).
