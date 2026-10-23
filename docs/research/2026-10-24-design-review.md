# Design review of the caret UI, 2026-10-24 (synthetic)

**Synthetic:** the reviewers are language-model personas briefed with screenshots of the design
lab (`claudish/web/design.html`), not people. Their value is breadth of perspective, not
evidence of what users do; real usage decides.

Reviewers: a Windows 11 designer (Fluent, the shell, Microsoft Pinyin), a macOS designer (HIG,
the system input methods), a GNOME designer (libadwaita, the Shell's IBus popup), a pinyin power
user (20 years, 8+ hours a day), an anti-AI novelist ("slop keyboard"), an accessibility
consultant (dyslexic, low vision, 150% scale), and a non-technical office manager. Each saw their
platform's mocks in light and dark.

## Round 1: what they agreed on

- The approval hid the thing being approved (the command was the faintest text); headers used
  three different patterns; "claude" was lowercase.
- Footer hints were too small and faint, and used three grammars ("Enter the first", a bare
  "1–2", "or type a reply" after a gap); "ask AI" read as salesy.
- Orange did four jobs: the AI tile, the selection bar, "failed", and the hosted dot; an error
  looked like branding.
- The highlight was too weak and depended on colour alone.
- After a rewrite, your original words were an 11 px grey footnote (the anti-AI writer: "your
  words are second-class, shown in pixels").
- Busy states had no way out; the mode switch showed one direction; macOS used PC key words.
- The panel seemed to move between states: an artefact of the mock clamping it inside its small
  window.
- The pinyin user: a reflexive 1 must never approve.

## Round 2

Every reviewer called the design ready to build (the office manager would leave it on; the
anti-AI writer: "now genuinely quieter than any AI writing tool I have used", with one condition,
below). New points, all adopted:

- The tinted highlight became the loudest thing on screen (writer), muddy in dark (Windows,
  macOS), foreign on a blue-accent desktop (GNOME): now a neutral fill with the platform's accent
  bar; the row's Enter key carries the meaning.
- The Enter key squeezed the highlighted row: a trailing column every row keeps.
- Failure in bold red was the one shouty thing: regular weight, with a warning mark.
- "cd" tile cryptic and too bright: neutral, matching the AI tile.
- "sent to Claude" read as if something was sent on your behalf: "from Claude · hosted".
- "or type a reply" under an approval was ambiguous: "or type why not" (typed words only refuse).
- macOS glyphs too small and faint: at the hint's size and contrast (to verify in SF Pro).

Split, and settled by design rather than by vote: whether the compose hints should fade. Two
wanted them kept (forgetting keys; a predictable panel), three wanted them gone after learning.
Decision: the hints appear when you pause, not while you type, and decision states always show
their keys. No counters, nothing learned, nothing to set.

Raised, outside the caret UI (for the settings and onboarding work): a per-app or per-document
"never suggest here" switch for continue (already possible with bindings; needs to be findable);
saying beforehand when a profile sends text to a hosted model; a first-run explanation and an
obvious way to pause; plain-language approvals for people who do not read commands.

## Round 5: Tab takes the model's text (2026-10-24)

The owner's split (Tab takes the model's text, Enter talks to the model) went to five CJK
input-method users (pinyin, Japanese, zhuyin, Wubi/Rime, Korean), the accessibility consultant and
the office manager, with the lab in every skin and the built Windows panel before and after a long
instruction. All seven: ship with changes. All seven expect to press Enter on drafts out of habit
(confirm in a Japanese IME, Hanja selection in Korean, OK in Office) for a week or two, and all
seven preferred a safe Enter to the old timing guard ("timing rules make an IME feel haunted"),
provided Enter is not silent: adopted as the lit Tab key. Six found "Tab keep · Esc undo" on the
rewrite contradictory: now "Tab insert · Esc dismiss". The accessibility consultant measured
keycap borders under 3:1: raised. Raised and open: the panel crossing the app window's edge,
truncated "You asked", rebindable keys (Rime), screen-reader announcements, and drafts in the
rigs echoing the instruction (the rigs' scripted backend, not a model).
