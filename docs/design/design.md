# cd_AI at the caret: the settled design

What the input method does and how it looks, on every platform. Conclusions only; how they were
reached (six review rounds, 2026-10-23/24) is in [research/](../research/). How a request is
answered is in [architecture.md](architecture.md).

**The web is the design.** `claudish/web/kit.css` and `kit.js` are the one look at the caret; the
demo uses it as is. The design lab (`claudish/web/design.html`, on the site at
`demo/design.html`) draws every state in a skin per platform (reference, Windows 11, macOS,
GNOME; light and dark), from the panel descriptions `claudish/composition.py` produces. A skin
changes only tokens (type, colours, shape, key names). A native input method passes a state when
its gallery screenshot matches the lab's mock of it (`design.html?platform=macos&state=drafts&solo`).
Where a platform cannot draw something, the design changes for all of them: no per-platform
substitutes.

## Scope

An input method, not a chat app: autocomplete while you type, a rewrite of what you composed, and
one-line instructions answered at the caret, with context carried between invocations in the same
text box. No chat window, transcript, history, slash menus, or supervised long tasks. The test for
new work: does it make one turn at the caret better?

## Two modes, one key grammar

A Shift tap (Shift pressed and released alone, not right after another key) switches mode, as
Shift switches English and pinyin. The taskbar, menu bar or top bar shows the mode all along; a
switch shows the mode's tile and name briefly at the caret ("compose · Shift continue").

- **Continue** (where cd_AI starts): keys go straight into the app. At a word boundary at the end
  of a line, the rest of the sentence shows in grey after the caret. Tab takes it; typing ignores
  it; Esc dismisses it. With nothing offered, Tab is the app's. Autocomplete only: no tools, no
  retrieval, no agent; its quality is its model's.
- **Compose**: your words are held as the platform's composition (one plain underline) until you
  choose, as in a CJK input method:

| Key | In compose |
| --- | --- |
| Tab | takes the model's text: asks for a rewrite (it waits in the panel; Tab again puts it in), inserts the highlighted draft, or an answer to read |
| Enter | talks to the model: sends your words as an instruction, a reply, or the answer to a question; it never inserts the model's text (on a draft it lights the row's Tab, the key that does) |
| Shift+Enter | keeps your words as typed |
| ↑ ↓ | move the highlight (no wrap); choices are not numbered: digits and Space are text |
| Esc | one step back: cancel the reply you typed, then edit the instruction, then drop it |
| Shift+Esc | brings back what Esc dropped, or the exchange a focus change held |
| F8 | attaches a picture of the window to the instruction |

Only a letter or a digit starts a composition; a space or punctuation with nothing composed goes
straight in. The compose keys show in the panel's footer from the first key (what Enter does must
be known before it is pressed).

## An exchange

1. **Enter sends** your words. They stay underlined at the caret while the exchange is open (as a
   CJK preedit: choices never show without a composition; macOS apps give an input method Return,
   Tab and the arrows only while there is marked text). The panel says what is happening
   ("working", with a spinner; Esc stop).
2. **The model answers** with drafts (rows; the first highlighted; Tab inserts the highlighted
   one), an answer to read (a paragraph; Tab insert, Esc dismiss, or type to ask more), or a
   question (its choices as rows; Enter answers with the highlighted one, or type a reply).
3. **A reply** you type takes the instruction's place in the composition; the panel then says
   "You asked: …" and the choices fade. After an answer, the panel says "You answered: …". The
   panel says only what the composition does not.
4. **An approval** (a tool that writes, a handoff to a helper) shows what will run in full; its
   safe choice (Deny, No) is listed first and nothing is highlighted: the first ↓ lands on Deny,
   so Allow is always a deliberate ↓↓ Enter. Typed words refuse it with a reason ("or type why
   not", then "Enter deny with reason").
5. **A focus change** commits what the composition shows (your own words), never the model's,
   never sends or approves; the exchange is held for that text box (its work goes on) and a passive
   pill shows on return ("3 drafts ready · Shift+Esc open"); it expires after ten minutes. A result
   never goes into another box.
6. **Nothing is lost silently:** a drop says "dropped · Shift+Esc restore".

A rewrite waits in the panel ("Rewrite"; Tab insert, Esc dismiss): the composition only ever
holds your own words, because apps commit a visible composition themselves (a click, a focus
change) and a rewrite there could reach your text without a key.

## The panel

One anatomy for every state: an optional thread ("You asked", "You answered": one line each, the
label muted, your words in the text colour); an optional header (a small label for who asks or
what this is, then the content as is, a command in monospace); rows; one footer (the AI tile, or a
warning mark on failure; what is happening; each key with its verb; free words such as "or type a
reply"; "from Claude · hosted" at the end when a hosted model answered).

- **The highlighted row:** a neutral fill, a bar in the platform's accent, and the key that takes
  it (Tab for a draft, Enter for a choice) in a trailing column every row keeps. Enter on a draft
  lights that key (the accent at 20% behind it, an accent outline) until a key changes the panel;
  the footer is never lit.
- **Failure:** the warning mark and the reason in plain words ("the model is offline"), regular
  weight; Tab retries a rewrite, Enter an instruction; Esc edit.
- **Colour:** Claudish orange means only AI (the tile); the highlight and the lit key use the
  platform's accent. Muted text 4.5:1 or more, the suggestion and keycap borders 3:1 or more; a
  forced-colors rendering keeps the bar and the key.
- **Placement:** under the line, its content starting where the composition starts (what IMK,
  TSF and IBus report while something is composed, as CJK candidate windows sit), or at the caret
  when nothing is composed; clamped to the screen, above the line when there is no room below. It
  stays where it opened while it is open (a sent instruction stays, and a reply takes its place,
  so it never jumps); it moves only if its anchor leaves that line or lands left of it. It never
  slides while you type. It fits its editor or screen. Panels follow the system theme, not the
  app's: on GNOME 46 that is the Shell's, which is always dark (the light GNOME skin is GNOME 47+).
- **Shape:** each platform draws the panel's own corners, border and shadow from its skin's tokens
  (no reliance on a compositor that may not draw them).

## What each platform cannot draw, and the design that follows

- The composition is the platform's plain underline (macOS cannot colour it; Wayland cannot style
  it), so a sent instruction looks like one being typed; the panel's "working" says it was sent.
- The suggestion is cd_AI's own grey text after the caret, in its UI font at the caret's height
  (only macOS reports the app's font), and only at the end of a line, so it never covers your text.
- Each platform reports where a composition starts (and the caret without one), so the panel
  anchors there everywhere.

## Sign-off checks the lab cannot make

Windows in Segoe UI Variable at 100%, 150% and 200%, in high contrast and over a dark app; macOS
in SF Pro, over a busy background, both appearances; GNOME from the Shell stylesheet, with text
scaling and caret rectangles on Wayland (GTK4, Electron, terminals). The galleries
(`tests/desktop/{windows,macos,linux-gnome}/gallery.sh`) take one screenshot per lab state.

## Open

The summon key (Enter or Shift+Enter, G47); how much context continue gets (G48); per-app input
profiles (G50: continue's Tab in macOS Terminal); replacing an instruction a focus change left in
the text when a draft is taken on return (G51); keeping the panel inside the app's window;
screen-reader announcements.
