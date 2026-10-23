# Persona poll, 2026-10-23

Five independent reviewers, each an agent in a persona, read the repository, the
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
