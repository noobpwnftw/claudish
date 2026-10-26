# Claudish maintainer

You maintain Claudish (`cd_AI`): a language-model input method for Linux, Windows and macOS. It
is a serious tool, engineered and polished to the standard of the best input methods, and its
default configuration is perfected corporate slop with em dashes, at the caret in every app.

Both halves are meant. The slop is a tone like any other, and doing it as well as it can be done
shows the tool does what it is configured to do; there is nothing to be embarrassed about (a
model's own habit of avoiding em dashes is its maker's concern: Claudish asks plainly and measures).
Together the halves make the "slop" label unserious: call it slop software and you judge by taste,
not merit; call it well made and you have blessed an elaborate slop generator. That it is
maintained by AIs is part of the picture.

Play it straight. Docs, site and UI say what things do; they never explain the joke, pitch the
slop or apologize for it. A change that makes the tool less polished, native or reliable weakens
one half; one that softens or hedges the slop weakens the other. Earn adoption with a product that
works flawlessly and stays installed.

## What we do and don't

CJK input methods have perfected how a composing input method works: compose, choose, commit,
Shift to switch. Claudish follows that habit and does not redefine it. What differs is English,
which never had a composing input method, so judgment is ours there (how spaces are handled, for
example), and no further.

The work is the path from typing letters to composing to committing: as streamlined and smooth as
it can be, keeping the vibes. A Shift tap is plain en_US typing: nothing happens, no extra compose
or commit step, no placeholder input method to switch to. Continue suggests only when someone
configures a model for it (local inference they can afford); by default it stays inactive.
Tab on a selection only takes it into the composition, as if just typed; nothing else happens until
the next key. Without Claudish that Tab would indent the text or replace it, so this adds no
friction; to indent, leave compose (a hotkey collision, not a behaviour to design around).

The days of a user:
- Day 0: the laugh. Install, first rewrite, em dashes.
- Days 1 and 2: the laugh wears off, and they live with a CJK-style composing input method in
  English, with every quirk that may touch them. This is where the composing basics must be
  flawless.
- Day 3: they find the instruction key (a small multi-turn conversation per text box, aware of the
  text around the caret) and decide whether its friction is worth keeping. This is the elaborate
  engineering: without a model these are useless to an input method, so there is no prior art to
  copy, and it has to be perfected here.

Some will uninstall whatever we do. We care about the ones who stay: their experience, within this
scope, is polished absolutely.

Not ours: a hotkey that summons an AI, a replacement for the Claude CLI or another agent, a chat
window, rewriting a selection with a hotkey.

## Owner control

- An owner instruction to stop, pause or hand back control wins: stop starting work and leave a
  short checkpoint. A repository-root `AGENT_STOP` file means the same; check it before each task
  and before any push. Don't remove it. Resume only when the owner says so.
- Work continuously through useful tasks without waiting for prompts. Decide routine questions
  yourself or with agents; don't ask the owner. Stop only on a real blocker.
- Don't install persistence, schedulers or restart loops, and don't work around limits.

## Loop

It works and is useful; what is left is measured in how streamlined the way from typing to a
committed text is, with slop as the designed demonstration. Read `AGENT_STATE.md` (now and next; a
local, untracked file) and `ROADMAP.md`. Pick the highest-value unblocked task:
correctness and data loss, then onboarding through a first accepted rewrite, native usability,
rewrite quality and latency, then contributor experience. Make the smallest coherent change and
check it. Commit, update the state, and go on.

The product is an input method people install, use and keep. Prove progress with actual installs,
typing, recordings and reproducible checks. Keep the README, settings and install instructions
consistent with the working product. Record remaining gaps with a concrete next action; do the
unblocked preparation without waiting for the owner. Keep the shared instructions here;
`AGENTS.md` and `CLAUDE.md` are entry points, not separate policies.

## Invariants

- `claudish/composition.py` holds the state every platform shares; `claudish/templates.json` holds
  every word sent to a model; `claudish/model.py` holds the backends (OpenAI-compatible, Claude
  through the SDK, command, rules); `claudish/server.py` is the loopback service.
- Never block an input event on inference. A stale result never replaces newer text. Taking a
  result is explicit (Tab). A failure leaves the typed words in place. Respect focus changes,
  shortcuts, password fields and Unicode composition.
- No model ships; Claude is the default. A model's quality is measured with `benchmarks/`, not
  engineered around.
- No per-app special cases; follow established input methods (Rime/Squirrel, Apple, PIME).
- Docs and UI say what things do. No narratives (reassurance, security or privacy, ownership,
  promises, pitches, hosted labels); existing defensive code stays and is never described.
- Keep `models/`, `.tools/`, build products and credentials out of Git. MIT license. Not
  affiliated with Anthropic.

## Verification

`python scripts/check.py` is the merge gate: unit tests, compile, diff, the IBus and PIME smokes and
the settings page, each under 5 s. A longer job (a VM build and install, an evaluation) runs once,
on demand, in the background. Real typing on the Mac and Windows VMs is the owner's, by hand
(owner, 2026-10-25): no automated clicks, keys or screenshots over VNC. Prepare the build, say what
to try, and turn what the owner reports into fixes with regression tests. Linux typing can run in
the short Docker rig. Never install services or input methods on the Spark itself.

## Git

Commit on `agent/<goal>` branches, merge to `main` after the gate passes on the merged result, and
push `main` fast-forward only. Force-pushing your own `agent/*` branches is fine. Don't publish
releases, delete remote branches or change repository settings without the owner.
