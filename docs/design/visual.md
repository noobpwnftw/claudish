# How cd_AI looks (G45)

An input method is on screen all day, in every app. The framework (docs/design/architecture.md)
decides *what* to show; this page decides how it looks.

**The web is the design (owner, 2026-10-24).** The look is made perfect in the browser first, then
the real input methods follow it to the pixel. `claudish/web/kit.css` is the one look at the caret
(the suggestion, the composition, the panel, the mode switch); the demo uses it as is. The design
lab (`claudish/web/design.html`, served at `/design.html` and on the site at `demo/design.html`)
draws every state below in a mock of each platform: the reference skin, Windows 11, macOS, and
GNOME, light and dark. A skin changes only tokens (type, surface, shape); the kit never changes per
platform. A platform passes a state when a screenshot of the real input method matches its mock
(`design.html?platform=windows&state=drafts&solo` shows one mock alone, at its size). Designs are
settled in the lab (and its polls) before any native drawing changes.

Screenshots of every state on each platform come from the galleries (`tests/desktop/linux-gnome/
gallery.sh`, `tests/desktop/windows/gallery.sh`, `tests/desktop/macos/gallery.sh`, into
`.tools/gallery/`). Before a visual change lands, the galleries are run again and read.

## Principles

1. **Your words and the machine's never look alike.** What you typed is plain text. What the model
   offers (the rest of the sentence, a rewrite, a draft) looks different at a glance, everywhere,
   and never looks committed until you take it.
2. **Quiet by default.** No permanent strip of hints. A hint appears only when a choice is
   waiting, says the one or two keys that matter, and stays short.
3. **The caret is where the eyes are.** What needs reading (a question, an answer, the drafts)
   appears next to the caret, sized to its content, in a readable size; nothing hides in a tray.
4. **One look, many platforms.** The same shapes, words, and order everywhere; where a platform
   cannot draw something, the next best thing, never something that misleads.
5. **The mode shows only when it matters.** While you compose, the composition says so; in
   continue, cd_AI is invisible until it offers something.

## The states

| State | Looks like |
| --- | --- |
| Continue, a suggestion | cd_AI's own grey text right after the caret, in its UI font at the caret's height, only at the end of a line; Tab takes it |
| Compose, typing | your words with the platform's own composition underline; from the first key the panel's footer starts with the AI tile (compose is visible) and says Tab rewrite · Enter ask · Shift+Enter keep |
| Compose, a rewrite | your words stay in your text; the rewrite waits in the panel ("Rewrite"); Tab puts it in, Esc or typing on keeps your words |
| Waiting | the composition as it is; the footer says what is happening ("rewriting…") |
| Drafts | your instruction still underlined at the caret: rows, the first highlighted (a neutral fill, an accent bar, the Tab key at its end); ↑↓ choose, Tab insert, Esc edit |
| A question | the question as is (a small label for who asks), its choices as rows, not numbered; ↑↓ choose, Enter answers; an approval highlights nothing and lists Deny first |
| An answer to read | the text as a short paragraph, wrapped to a readable width, with no rows; Tab insert, Esc dismiss, or type to ask more |
| Progress (an agent) | one muted footer line: what it is doing |
| Hosted model | a small mark at the footer's end when the answer came from a hosted model |
| A mode switch | the mode's tile and name, briefly, at the caret |

Every element is drawn by means every platform has (the lab's table, "How each platform draws
it"). Where a platform cannot draw one, the design changes for all of them: the composition is
the platform's plain underline (macOS cannot colour it, Wayland cannot style it), and the
suggestion is cd_AI's own text, not the app's (only macOS reports the app's font).

## Settled in review (2026-10-24, two rounds, seven synthetic reviewers)

The lab went through two rounds with a Windows, a macOS and a GNOME designer, a pinyin power user,
an anti-AI writer, an accessibility consultant and an office manager
([research/2026-10-24-design-review.md](../research/2026-10-24-design-review.md)). Decisions:

- **One panel anatomy:** an optional header (a small label for who asks or what this is, then the
  content as is), rows, one footer. The footer is the AI tile, then each key with its verb, then
  free text ("or type a reply"). (Since round 4 the rows are not numbered, and the highlighted
  row's key is the one that takes it: Tab for the model's text, Enter for an answer.) Key names are a
  skin token (macOS ↩ ⎋ ⇥ without boxes, at the hint's size and contrast; Windows and GNOME words
  in keycaps).
- **The highlighted row** is a neutral fill with a bar in **the platform's accent** and its own
  Enter key in a trailing column every row keeps (so rows wrap alike and the cue is not colour
  alone). Claudish orange means only AI: the tile.
- **Approvals and handoffs:** the label says who asks ("Claude Code wants to run", "Hand off to
  Claude Code"); what is approved is the body, at full contrast (a command in monospace); the safe
  choice is listed first (Deny, No); nothing is highlighted, so Enter alone never approves; typed
  words are a refusal with a reason ("or type why not", then "Enter deny with reason").
- **Your words are never smaller than the machine's:** after a rewrite the panel shows "Your
  words" at full size and contrast.
- **Failure:** a warning mark instead of the AI tile, the reason in the platform's error colour,
  regular weight ("The model is offline").
- **Busy:** a small spinner (the platform's own where it has one), what is happening, Esc: stop.
- **Hosted:** plain words at the footer's end ("from Claude · hosted").
- **The compose hints show from the first key** (round 4, the CJK users: what Enter does must be
  visible before you press it; round 2 had them wait for a pause). States that need a decision
  (questions, approvals, failures) always show their keys. Whether hints fade as you learn the
  keys was settled for the hints alone; learning how you write belongs to the model, if users ask
  for it (G49).
- **Mode switch:** the mode's tile, its name, and the key back ("Compose · Shift back"); continue's
  tile is neutral. The taskbar, menu bar or top bar shows the mode all along.
- **Space** in compose types a space; it never picks a candidate.
- **Contrast:** muted text 4.5:1 or more, the suggestion 3:1 or more; a forced-colors rendering
  keeps the bar and the Enter key.
- **A panel opens under the caret and stays where it opened until it closes** (its content
  starting at the caret, clamped to the screen, above the line when there is no room below); it
  moves only if the caret leaves that line or lands left of the panel's start, as when a long
  instruction is sent and its text leaves (owner, 2026-10-24): then it moves once, to the caret.
  It never slides while you type. GNOME reports only
  the caret, not where the composition starts, so no platform anchors to the composition.

**After an instruction is sent (round 3, the same reviewers):**

- **A sent instruction stays the composition while its exchange is open** (owner, 2026-10-24,
  reversing round 3's "it leaves your text"): as in a CJK input method, choices never show
  without a composition. macOS apps pass an input method Return, Tab and the arrows only while
  there is marked text, and not reliably (Terminal never, a Notes title sometimes); so on every
  platform. A reply you type takes its place; a focus change commits what it shows (your own
  words) and holds the exchange. "You asked" shows in the panel only once the composition no
  longer says it (a reply, an answer): to be polled.
- **The panel is the exchange, not a chat:** your earlier turns ("You asked", "You answered") as
  context, one line each, muted, at full size, with a neutral rule beside them; the current turn
  (a question, a command to approve, the drafts, an answer) at full contrast. Only the first "You
  asked" and the latest turn show; turns between fold into one line.
- **Typing a reply goes where typing goes: the caret.** The reply is the composition; the
  choices keep their words and lose their numbers; the footer says Enter sends it.
- **Keys (round 4: five CJK input-method users, who weigh most on how an input method behaves;
  owner, 2026-10-24):** **choices are not numbered.** In pinyin digits are free to be select keys;
  in English they are text, as Space is, and "2 + Enter" is no shorter than "↓ + Enter". So ↑ and ↓
  move the highlight (no wrap), Enter takes an answer (Tab a draft: see below), a click picks; digits are always text (a reply
  that starts "2 tests are flaky" is a reply). An approval starts with nothing highlighted: the
  first ↓ lands on its safe choice, Enter does nothing until a row is highlighted, so Allow is
  always a deliberate ↓↓ Enter. Space while composing is text; with nothing typed while choices
  show, it does nothing. Compose shows what Enter does from the first key ("Tab rewrite · Enter
  ask · Shift+Enter keep"), since Enter sends your words away. A Shift pressed right after
  another key (rolled typing, Korean ㅃ) is not a mode tap. **Esc, one ladder:** a reply composed, Esc cancels it; else Esc edits (the
  instruction comes back to the caret); in editing, Esc drops it; while working, Esc stops.
- **Focus:** leaving the text box hides the panel; the work goes on; returning shows it again
  where it was, and Esc still brings the instruction back. A result never goes into another box.
- **Nothing is lost silently:** a clear or a drop says "Dropped · Shift+Esc restore", and
  Shift+Esc brings back a dropped instruction or a cleared reply. In the thread your words are in
  the text colour, underlined as they were at the caret (your composition, moved into the panel);
  the labels are the muted part. (A neutral rule beside them read as a second caret.)
- **A rewrite waits in the panel (owner, 2026-10-24):** the composition always holds your words;
  Tab shows the rewrite in the panel ("Rewrite"), Tab again puts it in. Apps commit the visible
  composition themselves (a browser, a classic Win32 control, a click in a Mac text view, IBus on
  focus-out), so a rewrite in the composition could reach your text without a key.
- **Focus changes (seven reviewers, unanimous):** a focus change may commit your own words for the
  document, never the model's words, never words meant for the model, and it never sends or
  approves. Composing: your words go in as typed. A rewrite showing: your words. An instruction
  sent: the exchange is held for that text box (a question or an approval waits; results go to
  it); a reply you were typing is not inserted. The grey suggestion disappears. Back in that text
  box (or app, where no box can be told apart): a passive pill ("3 drafts ready · Shift+Esc
  open") that takes no keys; Shift+Esc opens the exchange (asking again if it was still working);
  it expires after ten minutes. A result is never inserted into another box.
- **Tab takes the model's text; Enter talks to the model (owner, 2026-10-24).** Tab: continue's
  suggestion, a rewrite, the highlighted draft, an answer to read. Enter: send an instruction, a
  reply, the answer to a question. Enter never inserts the model's words, so a reflexive second
  Enter after sending inserts nothing (the double-Enter guard is gone).
- **Round 5 (seven reviewers: five CJK input-method users, accessibility, an office manager;
  2026-10-24)** agreed with the split; every one asked that Enter on the model's text not be a
  silent dead key. **Enter on a draft lights the highlighted row's Tab**, the key that takes it
  (the accent at 20% behind it, an accent border, the text at full contrast), until a key changes
  the panel. The footer is not lit: it is three keys, not thirty (owner); a rewrite or an answer,
  which have no row, light nothing. No insert, no resend, no sound, no
  animation. The rewrite's keys are **Tab insert · Esc dismiss** ("keep" meant your own words on
  Shift+Enter; "undo" undid nothing). Keycap borders are 3:1 or more on every skin; macOS draws its
  key glyphs at the text's size and colour. Open: keeping the panel inside the app's window
  (all seven noticed it crossing Notepad's edge), the full instruction instead of one line, and
  rebindable keys.
- **Shadows (owner, 2026-10-24):** every platform draws the panel's own shadow, corners and border
  from the skin's tokens. Windows did rely on DWM, which gives a popup none of them without a
  GPU (a VM) or on Windows 10; the panel is now a layered window that paints them (Panel.cpp),
  as GNOME's stylesheet and macOS's NSPanel already did.
- **Words:** "Esc edit" after a result or a failure; the mode switch names where Shift goes
  ("Shift continue"); under an answer to read, "or type to ask more".
- **Panels follow the system theme,** not the app under the caret (a light panel over a dark
  terminal in light mode is expected).

Checks the mock cannot make, before a platform signs off: Windows in Segoe UI Variable at 100%,
150% and 200% scale, in high contrast and over Notepad's dark theme; macOS glyphs in SF Pro and
the menu material over a busy background in both appearances; GNOME colours from the Shell
stylesheet, text scaling, and caret rectangles on Wayland (GTK4, Electron, terminals).

## Order of work

1. The lab: every state, every skin, both themes, until each passes review.
2. The demo on the kit (the reference skin, live).
3. Windows: Claudish's PIME (the only one supported) draws the panel to the Windows 11 mock;
   display attributes draw the suggestion and the composition.
4. macOS: the panel and overlay to the macOS mock.
5. Linux: a GNOME Shell extension draws the panel to the GNOME mock; attributes on X11.
6. The home page, matched to the result.
