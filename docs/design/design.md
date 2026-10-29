# cd_AI at the caret: the design

What the input method does and how it looks, on every platform. Conclusions only; how they were
reached is in [research/](../research/). How a request is
answered is in [architecture.md](architecture.md).

**The web is the design.** `claudish/web/kit.css` and `kit.js` are the one look at the caret; the
demo uses it as is. The design lab (`claudish/web/design.html`, on the site at
`demo/design.html`) draws every state in a skin per platform (reference, Windows 11, macOS,
GNOME; light and dark), from the panel descriptions `claudish/composition.py` produces. A skin
changes only tokens (type, colors, shape, key names). A native input method passes a state when
it matches the lab's mock of it (`design.html?platform=macos&state=drafts&solo`), checked by hand.
Where a platform cannot draw something, the design changes for all of them: no per-platform
substitutes.

## Scope

An English input method, not a chat app (other languages keep their own input methods, switched to as
usual; cd_AI does not rebuild them): autocomplete while you type, a rewrite of what you composed, and
one-line instructions answered at the caret, with context carried between invocations in the same
text box. No chat window, transcript, history, slash menus, or supervised long tasks. The test for
new work: does it make one turn at the caret better?

What the model is told, the tone included, is data (`claudish/templates.json`, amended per
profile): corporate slop by default, or a salesman, a critic, a bard, proofread, or a described
tone.

## Two modes, one key grammar

A Shift tap (Shift pressed and released alone, not right after another key) switches mode, as
Shift switches English and pinyin. The taskbar, menu bar or top bar shows the mode all along. On
Linux and Windows a switch shows the mode's tile and name briefly at the caret ("compose · Shift
continue"); like every toast, it lasts two seconds or until the next key, since it was said where
the caret was. On macOS the system announces the new input mode at the caret, so cd_AI's toast is
off there.

- **Compose** (where cd_AI starts): your words are held as the platform's composition (one plain
  underline) until you choose, as in a CJK input method.
- **Continue**: keys go straight into the app. At a word boundary at the end of a line, the rest
  of the sentence shows in gray after the caret. Tab takes it; typing ignores it; Esc dismisses
  it. With nothing offered, Tab is the app's. Autocomplete only: no tools, no retrieval, no agent;
  its quality is its model's. It suggests only with a model set up for it (a local one, or one a
  profile routes); otherwise it types as is.

cd_AI ships no model: compose uses the profile's model (Claude by default). With none, compose says "no model is set up".

The keys, each in full: [using.md](../using.md#typing). In short: Tab takes what the model offers
(a rewrite waits in the panel first), Shift+Enter talks to the model, Enter keeps your words as
typed, ↑ ↓ move the highlight, ← → move in what you type, Esc steps back, Shift+Esc brings back, F8
adds a picture. Once the model answered (a rewrite, drafts, an answer to read, a question), what you
type is about its answer: a follow-up or a reply, about the draft in view; Esc goes back to your
words. Each panel says what typing does.

Shift+Enter asks and Enter keeps by default (owner, 2026-10-25, after a poll: Enter is the key
people send and confirm with); `"keys"` swaps them.

A composition is one line (owner, 2026-10-25): finish it, or keep it with Enter and start the next
line, which is the app's. So Shift+Enter with words composed asks the model, though chat boxes use it
for a newline; with nothing composed it is the app's newline.

Only a letter or a digit starts a composition; a space or punctuation with nothing composed goes
straight in. The compose keys show in the panel's footer from the first key (what each Enter does must
be known before it is pressed).

## An exchange

1. **Shift+Enter sends** your words. They stay underlined at the caret while the exchange is open (as a
   CJK preedit: choices never show without a composition; macOS apps give an input method Return,
   Tab and the arrows only while there is marked text). The panel says what is happening
   ("working", with a spinner; Esc stop).
2. **The model answers** with drafts (rows; the first highlighted; Tab inserts the highlighted
   one), an answer to read (a paragraph; Tab insert, Esc dismiss, or type to ask more), or a
   question (its choices as rows; Tab answers with the highlighted one, or type a reply). The
   panel stays shorter than a screen (about 24 rows): past it, the drafts not highlighted show their
   first two rows and a longer text ends in an ellipsis; Tab inserts the whole text
   (`state=long-drafts` in the lab).
3. **A reply** you type takes the instruction's place in the composition; the panel then says
   "You asked: …" and the choices fade. After an answer, the panel says "You answered: …". The
   panel says only what the composition does not.
4. **An approval** (a tool that writes, a handoff to a helper) shows what will run in full; its
   safe choice (Deny, No) is listed first and nothing is highlighted: the first ↓ lands on Deny,
   so Allow is always a deliberate ↓↓ Tab. Typed words refuse it with a reason ("or type why
   not", then "Shift+Enter deny with reason").
5. **A focus change** commits words you are typing; a sent instruction is cleared, and its exchange is held for that text box
   and a passive pill shows on return ("3 drafts ready · Shift+Esc open"); it expires after ten
   minutes.
6. **A drop** says "dropped · Shift+Esc restore".

A rewrite waits in the panel ("Rewrite"; Tab insert, Esc dismiss); the composition holds your
words.

## The panel

One anatomy for every state: an optional thread ("You asked", "You answered": one line each, the
label muted, your words in the text color); an optional header (a small label for who asks or
what this is, then the content as is, a command in monospace); rows; one footer (the AI tile, or a
warning mark on failure; what is happening; each key with its verb; free words such as "or type a
reply").

- **The highlighted row:** a neutral fill, a bar in the platform's accent, and the key that takes
  it (Tab, for a draft or a choice) in a trailing column every row keeps. Enter on a draft
  lights that key (the accent at 20% behind it, an accent outline) until a key changes the panel;
  the footer is never lit.
- **Failure:** the warning mark and the reason in plain words ("the model is offline"), regular
  weight; Tab retries a rewrite, Shift+Enter an instruction; Esc edit.
- **Color:** Claudish orange means only AI (the tile); the highlight and the lit key use the
  platform's accent. Muted text 4.5:1 or more, the suggestion and keycap borders 3:1 or more; a
  forced-colors rendering keeps the bar and the key.
- **Placement:** under the line, its content starting where the composition starts (what IMK,
  TSF and IBus report while something is composed, as CJK candidate windows sit), or at the caret
  when nothing is composed; clamped to the screen, above the line when there is no room below. It
  stays where it opened while it is open (a sent instruction stays, and a reply takes its place,
  so it never jumps); it moves only if its anchor leaves that line or lands left of it. It never
  slides while you type. It fits its editor or screen, not the app's window. Panels follow the system theme, not the
  app's: on GNOME 46 that is the Shell's, which is always dark (the light GNOME skin is GNOME 47+).
- **Shape:** each platform draws the panel's own corners, border and shadow from its skin's tokens
  (no reliance on a compositor that may not draw them).

## What each platform cannot draw, and the design that follows

- The composition is the platform's plain underline (macOS cannot color it; Wayland cannot style
  it), so a sent instruction looks like one being typed; the panel's "working" says it was sent.
- The suggestion is cd_AI's own gray text after the caret, in its UI font at the caret's height
  (only macOS reports the app's font), and only at the end of a line.
- Each platform reports where a composition starts (and the caret without one), so the panel
  anchors there everywhere.

## Sign-off checks the lab cannot make

Windows in Segoe UI Variable at 100%, 150% and 200%, in high contrast and over a dark app; macOS
in SF Pro, over a busy background, both appearances; GNOME from the Shell stylesheet, with text
scaling and caret rectangles on Wayland (GTK4, Electron, terminals).

## Open

How much context continue gets; per-app input behavior (first, continue's Tab in macOS
Terminal); screen-reader announcements.
