# Changelog

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
