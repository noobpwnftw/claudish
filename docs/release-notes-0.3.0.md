# cd_AI 0.3.0

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

## Download

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway**. With Windows' **Smart App Control** fully on (not in evaluation), an
unsigned installer is blocked with no Run anyway.

| | File |
| --- | --- |
| macOS 26, Apple silicon (not Intel yet) | `cd_AI.pkg` |
| Windows 11, x64 and ARM64 | `cd_AI-setup.exe` |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.3.0/scripts/install.sh \| sh` |
