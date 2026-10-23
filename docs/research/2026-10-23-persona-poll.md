# Synthetic persona poll, 2026-10-23

Not real users: five independent reviewers, each an agent playing a persona, read the repository, the
site, and the demo (read-only) and judged utility, onboarding, daily-flow risk,
retention, and meme factor. Owner's brief: a social experiment; adjust the
roadmap with judgement, and keep the line where Claudish hands off to dedicated
AI apps.

| Persona | Keeps it after 30 days | With their top changes |
| --- | --- | --- |
| Everyday Mac writer (Slack, Gmail, Docs; never installed an IME) | 1/10 (never finishes installing) | 5/10 |
| Power-user developer (VS Code, Claude Code, tmux, local models, MCP) | 4/10 | 7/10 |
| Chinese pinyin user (15 years of Sogou/Rime; writes English at work) | 4/10 | 7/10 |
| Tech critic (HN, newsletters) | spreads 7/10, still used 3/10 | 5–6/10 |
| Privacy-minded SRE (GNOME, Windows at work, SSH) | 4/10 | 6/10 |

## Where they agreed

- **Installing is the wall.** Clone, Python, an unsigned bundle, log out and in,
  adding an input source by hand: every persona but the developer would stop
  there. Signed packages per platform (and a real uninstall) come before features.
- **Instruct at the caret is the product.** "Tell the team the deploy slips to
  Friday", Enter, pick 2, is the round trip people make to a chat tab ten times
  a day. The terminal "fix" with no shell hook impressed the developer, the SRE,
  and the critic. Rewrite is a party trick for native speakers, but the key
  feature for an ESL writer.
- **Trust is binary.** An input method that ever eats a key, surprises, or lags
  is uninstalled the same hour; "a keylogger with an LLM" is the first comment.
- **The em-dash joke** gets the click and should stay on the front door, but
  not in what people send at work (a plain register by default was asked for by
  three of five).
- **No chat window, no proactive agents, no long tasks at the caret.** Hand off
  to dedicated apps (Claude Code) instead, and make that handoff a real action.

## Found and fixed the same day

- The local API took sessions, answers, and text-box requests from any local
  process, so another process could make the service read a terminal or answer
  an agent's question. Now a per-run token in a file only the user can read
  (G36).
- A terminal screen at a password prompt (sudo, ssh, gpg) is no longer sent.
- Shift+Enter "keep as typed" turned `-` into `—`; hyphens now stay as typed.
- Documentation drift: the install key table, F7 in the changelog, the macOS
  status on the site.

## The owner's answers

- **Space stays a space** in English compose ("it ain't a pinyin IME"); negotiated
  with the pinyin persona, who withdrew "Space picks draft 1" and asked instead
  that a reflexive space not throw away drafts: while drafts show, a space is
  held and keeps them, and Enter right after the drafts appear waits (a
  double-tapped Enter never inserts a draft nobody read). Both done. The persona
  also withdrew "Enter as instruct is the biggest break": nothing reaches the app
  without a visible draft step. Still open: an "AI›" mark at the caret while
  composing (visual pass).
- **The Claudish voice is the default**, it is the identity; a profile's `tone`
  sets another (done).
- **Releases:** internal beta until it is robust enough to ship (G37), not a
  blocker.

# Round 2: the hostile and the unsavvy

Owner's brief: hear from the most anti-AI people ("slop keyboard"), and pitch
the same page to people who are not technical, then use what we learn to fix
designs and goals before polishing details. Synthetic again: agents in personas.

| Persona | Try / install | A month later, or "stop mocking it" |
| --- | --- | --- |
| Anti-AI writer and editor (newsletter, teaches writing) | install 2/10 | stop mocking 3/10 (6 with the em-dash voice opt-in) |
| Anti-AI open-source developer (C library, Emacs) | install 2/10 | stop calling it slop 5/10 ("the engineering isn't slop; the premise and the defaults are") |
| Bakery owner, 52, Windows, never heard of an input method | try 6/10 if someone sets it up | 3/10 (6 with a visible button and plain tones) |
| Field operations manager with dyslexia and RSI | try 5/10 (demo only) | 2/10 (7 with fix-only, plain, an installer) |

## What they agreed on

- **The default voice is the sticking point for everyone outside tech.** The
  writer: "the joke is the product spec"; the dyslexic manager is afraid of
  sounding like a robot; the bakery owner: "of utmost significance from the
  bakery lady would sound like I've got a lawyer". The owner's call: the
  Claudish voice stays the default (identity); people choose another tone.
- **What people actually want rewrite to do** is correct, not polish: "fix my
  spelling, keep my words" (dyslexia), "clear and polite" (bakery).
- **Continue, everywhere, by default** distracts a dyslexic writer mid-sentence,
  is "a keyboard that thinks at me" to the skeptic, and sends text at every
  pause. Its template also contradicts itself: "the same voice, polished and
  slightly verbose".
- **The page speaks to programmers.** "Input method", "model", "API key",
  "deploy", "MCP" lost both non-technical personas; the accessibility story
  ("help at the caret, no switching windows, your words one key away, fewer
  keystrokes") is the strongest pitch for them and it is not on the page.
  The demo does not say 491 MB before the button.
- **Never send anything without my click** (all four), and **never add facts or
  promises** I did not type (the drafts' "more soon", "details to follow").
- **Be transparent:** say the project is AI-maintained, and label these polls
  synthetic.

## Done the same day

- Tone presets: `"fix"` (correct spelling, typos, grammar; keep the words) and
  `"plain"`; `claudish setup --tone`. On Qwen 1.5B, "pump 3 trippd agian at 1400,
  reset by mark, no injurys" → "pump 3 tripped again at 1400, reset by mark, no
  injuries" with fix, while the Claudish voice made it "Please pump three times
  again…".
- Instructions add no facts, promises, or commitments the user did not give.
- Secrets already on a terminal screen (keys, tokens, `PASSWORD=`, private keys)
  are redacted before it is sent.
- The README says the project is AI-maintained; these notes say they are synthetic.

## Raised for the owner

- Should continue mirror the writer's own voice (the Claudish voice staying in
  rewrite and instruct), as its template already half-says?
- Should continue start on everywhere, or per app (G38), with long-form editors
  quiet by default?
- A second audience on the home page: the accessibility and everyday angle,
  in plain words, next to the joke.
