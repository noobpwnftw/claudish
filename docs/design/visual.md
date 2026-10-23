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
| Continue, a suggestion | the rest of the sentence after the caret, in a muted grey, no underline; Tab takes it |
| Compose, typing | your words with the composition's underline in the accent colour (so compose is visible at the caret) |
| Compose, rewrite in place | the rewrite in the same place, with the accent underline and a faint accent tint behind it (not your words) |
| Compose, waiting | the composition as it is, and a small "…" after it while the model works |
| Drafts | a list next to the caret: number, draft; the first highlighted; one short hint line (1–3, Esc) |
| A question | the question as is, its choices numbered below, one short hint line |
| An answer to read | the text as a short paragraph, wrapped to a readable width, then Insert it / Dismiss |
| Progress (an agent) | one muted line: what it is doing |
| Hosted model | a small mark in the hint line when the answer came from a hosted model |

## What each platform can draw

| | Linux, X11 (GTK, Qt) | Linux, GNOME on Wayland | Windows (Claudish's PIME) | macOS (IMK) |
| --- | --- | --- | --- | --- |
| Colour in the composition | yes (IBus attributes) | no: text-input carries text and a cursor only | yes, with TSF display attributes (needs our PIME patch) | no: IMK drops colour; underline styles only |
| A window at the caret | IBus's popup (the panel's) | GNOME Shell's popup: labels, orientation, aux text | PIME's candidate window (C++, ours to restyle) | our own panel (NSPanel) at the caret rect |
| Suggestion after the caret | inline grey | in the popup, one line ("⇥ the rest"), not inline | inline grey (display attribute) | our own overlay at the caret: grey text in the app's size |

So: macOS and Windows can reach the reference look with code we own (a panel and an overlay on
macOS; display attributes and a restyled candidate window in Claudish's PIME). GNOME on Wayland is
limited by the protocol: there the suggestion goes in the shell's popup rather than inline, where
it would look exactly like typed text.

## Order of work

1. The lab: every state, every skin, both themes, until each passes review.
2. The demo on the kit (the reference skin, live).
3. Windows: Claudish's PIME (the only one supported) draws the panel to the Windows 11 mock;
   display attributes draw the suggestion and the composition.
4. macOS: the panel and overlay to the macOS mock.
5. Linux: a GNOME Shell extension draws the panel to the GNOME mock; attributes on X11.
6. The home page, matched to the result.
