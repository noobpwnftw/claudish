# Changelog

## Unreleased

- Tab on a selection, with nothing composed, makes it your words, as if you had just typed them:
  then Tab rewrites them, Shift+Enter sends them, Enter keeps them.
- A rewrite of words with text around them (a selection, or words typed mid-sentence) is written for
  their place: the model sees them marked in the text and replaces only that part.

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
