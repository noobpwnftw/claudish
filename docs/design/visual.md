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
| Compose, typing | your words with the platform's own composition underline; the panel's footer starts with the AI tile (compose is visible) and says Tab: rewrite, Enter: ask AI |
| Compose, rewrite in place | the rewrite in place of your words; the panel shows "was" and your words, Tab: keep, Esc: undo |
| Waiting | the composition as it is; the footer says what is happening ("rewriting…") |
| Drafts | rows: a muted number, the draft; the first highlighted (a soft fill, an accent bar); 1–3: pick, Esc: back |
| A question | the question as is (a small label for who asks), its choices numbered; an approval highlights nothing |
| An answer to read | the text as a short paragraph, wrapped to a readable width, then Insert it / Dismiss |
| Progress (an agent) | one muted footer line: what it is doing |
| Hosted model | a small mark at the footer's end when the answer came from a hosted model |
| A mode switch | the mode's tile and name, briefly, at the caret |

Every element is drawn by means every platform has (the lab's table, "How each platform draws
it"). Where a platform cannot draw one, the design changes for all of them: the composition is
the platform's plain underline (macOS cannot colour it, Wayland cannot style it), and the
suggestion is cd_AI's own text, not the app's (only macOS reports the app's font).

## Order of work

1. The lab: every state, every skin, both themes, until each passes review.
2. The demo on the kit (the reference skin, live).
3. Windows: Claudish's PIME (the only one supported) draws the panel to the Windows 11 mock;
   display attributes draw the suggestion and the composition.
4. macOS: the panel and overlay to the macOS mock.
5. Linux: a GNOME Shell extension draws the panel to the GNOME mock; attributes on X11.
6. The home page, matched to the result.
