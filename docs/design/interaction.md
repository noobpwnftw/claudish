# Design: the input method as the way you talk to machines

Status: proposal, 2026-10-22. Owner direction; maintained in ROADMAP as G18–G19.

## The idea

We operate computers with a keyboard and a mouse, and in a terminal only the
keyboard. Every app that takes text already has a text field, a caret, and an
input method between your keys and that field. An agent CLI is a text box and
Enter. Even its "interactive" parts are small choices: yes, no, or something
else.

An input method already has every piece of that interaction:

| An agent needs | An input method already has |
| --- | --- |
| a prompt you type | the composition, held and editable until you commit |
| send | Enter |
| the answer, before it lands | the candidate window |
| a choice (yes / no / other) | the candidate list: number keys, arrows, Enter |
| progress and status | the auxiliary text, or a status line in the candidate window |
| "put the result here" | commit at the caret, which becomes one undo step in the app |
| cancel | Esc |

So anything more capable than a flat notepad can host the whole loop, and it
works the same in an editor, a browser, a chat app, or a terminal. Users of
Chinese and Japanese input methods have used these exact controls (candidates,
number keys, Enter, Esc) all day for decades. None of it is new to them.

## Three layers, one key grammar

| Layer | Mode | You type | Requests | You get |
| --- | --- | --- | --- | --- |
| 1. Translation | `rewrite` | a phrase | on every pause | the phrase in Claudish |
| 2. Autocomplete | `continue` | the start of a sentence | on every pause | your text plus the next words |
| 3. Instruction | `instruct` | a command | on Enter only | the result, at the caret |

The keys are the same everywhere, on every platform:

- **F7** switches mode while composing.
- **Tab** accepts the candidate.
- **Enter** keeps your wording in layers 1 and 2. In layer 3 it sends; when the
  result is ready, Enter inserts it.
- **Esc** keeps what you typed, in every mode.
- **1–9** pick a choice when the candidate window shows a list (G18).

Invariants: nothing lands in your app without a key you pressed, your own text
is always one key away, a stale result never replaces newer text, and secure
fields are never touched.

## Layer 3, interactive: an agent session at the caret (G18)

Today, instruct mode runs one request (`--backend command`, for example
`claude -p`). An interactive agent asks questions as it works: whether a tool
may run, which of several options to take, what is unclear. The design runs an
agent **session** behind the composition and maps every turn onto input-method
controls.

### What it looks like

```
  write a release note from the last 5 commits▮          ← composition (your prompt)
 ┌──────────────────────────────────────────────────────┐
 │ instruct · working… Reading git log (2 of 3 steps)    │  ← auxiliary text: live progress
 └──────────────────────────────────────────────────────┘
```

The agent asks for permission:

```
  write a release note from the last 5 commits▮
 ┌──────────────────────────────────────────────────────┐
 │ Run `git log -5 --oneline`?                           │
 │ 1 Yes   2 Yes, for this session   3 No   4 Tell it…   │  ← candidate list: number keys
 └──────────────────────────────────────────────────────┘
```

Pressing 4 ("Tell it…") reopens the composition for a free-text answer; Enter
sends that answer into the same session. When the agent finishes:

```
  write a release note from the last 5 commits▮
 ┌──────────────────────────────────────────────────────┐
 │ Enter inserts:                                         │
 │ This release—modest in scope, considerable in care—   │
 │ adds context providers, invocation modes, and…  (12 ¶) │  ← preview; Enter commits all of it
 └──────────────────────────────────────────────────────┘
```

Enter commits the whole result as one undo step. Esc returns to your prompt;
press Esc again to keep it as typed, or edit it and press Enter for another
turn in the same session.

### How it works

```
adapter ──/sessions──▶ service ──stdin/stdout (stream-json)──▶ agent CLI
   ▲  candidate list,      │  events: progress, question,          (claude --print
   │  aux text, commit     │  partial text, result, error           --input-format stream-json
   └──── poll / events ────┘                                        --output-format stream-json
                                                                    --permission-prompts host)
```

- **Service.** A session API sits next to `/suggest`: `POST /sessions` (prompt,
  mode, profile), `GET /sessions/{id}/events` (long poll; PIME polls on key
  events), and `POST /sessions/{id}/answer` (a choice or free text). One
  session per focused text field; it ends on commit, Esc, or focus loss.
- **Agent bridge.** For Claude Code: run it with stream-json input and output,
  `--include-partial-messages`, and `--permission-prompts host`. The service is
  the host: each permission request becomes a `question` event with choices,
  and the answer goes back on stdin. `--session-id` keeps follow-up turns in one
  conversation. Other agents plug in through the same event model; plain
  single-shot commands keep today's `command` backend.
- **Adapters.** They render events with what each platform has: IBus lookup
  table and auxiliary text; TSF candidate list (PIME `setCandidateList`,
  `showMessage`); IMK candidate panel. Number keys select when a list is shown
  and type digits otherwise.
- **Terminal.** In a terminal, the result of an instruction is usually a
  command. It lands at the prompt like typed text, and running it is your
  Enter, never the input method's. `claudish fix` is the first instance of this.

### Safety

- Tool permissions stay with the agent, and the input method only relays your
  answer. Side-effecting tools always need an explicit choice; "for this
  session" lasts only until the session ends.
- The candidate window shows what was consulted (files read, commands run) next
  to the result.
- Secure fields never start sessions. Hosted backends are labelled, and text goes
  only to the backend the profile names.
- Cost and time are bounded per session (profile `timeout`, plus a turn limit).

### Open questions

- Long results: the candidate window has room for a preview, not a document.
  Keep the preview with a paragraph count (as above), plus a "show all" key that
  opens a scrollable panel?
- Where answers come from when a session outlives focus (you switch apps while
  it works): queue the result and show it when focus returns, or discard it?
- Wayland: IBus behavior differs across compositors; the session UI needs a
  test there.

## Onboarding (G19)

People already know how to use this: you type. Onboarding should take three
minutes, in this order:

1. **Try the three layers in the browser.** `python scripts/start.py` and open
   the demo. Each mode has its own sample phrases, and a one-line explanation of
   what Enter and Tab do in it.
2. **Pick a brain.** `claudish init` writes a starter config with commented
   profiles: local (default), any OpenAI-compatible server, Claude, and an agent
   CLI. It switches nothing on that you did not choose.
3. **Install for your OS.** One command per platform, then add **cd_AI —
   Claudish** in Input Sources.
4. **Learn four keys:** F7, Tab, Enter, and Esc. Everything else is typing.
