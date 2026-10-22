# Design: the input method as the way you talk to machines

Status: proposal, 2026-10-22. Owner direction; maintained in ROADMAP as G18–G19.

## Scope: an input method, not a chat app

Owner, 2026-10-23: "this is an IME, it does not bring a chat window, you do that
in a real app, we do turn based autocompletes and one line tasks extremely well,
and have some context along the invocations, that's all we gonna do."

- **In:** suggestions while you type (continue, rewrite); one-line tasks typed at
  the caret (instruct), answered with drafts to pick; small choices in the
  candidate list (an agent's permission question); and context carried between
  invocations in the same text box (earlier instructions, tool results, the text
  box itself) so a follow-up works.
- **Out:** a chat window, a transcript you scroll or reopen, a history browser,
  panels, slash-command menus, long-running tasks you supervise, or anything
  else that belongs in a real app. The agent's loop runs out of sight; what you
  see is a status line, a question, and drafts.
- **Test for new work:** does it make one turn at the caret better? If it needs a
  surface beyond the composition, the candidate list, and the status line, it is
  out of scope.

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

So anything more capable than a flat notepad can host a turn of the loop, and it
works the same in an editor, a browser, a chat app, or a terminal. Users of
Chinese and Japanese input methods have used these exact controls (candidates,
number keys, Enter, Esc) all day for decades. None of it is new to them.

### Principle: you take the initiative

Claudish does not summon an assistant, and you do not hand your workspace to an
agent. It changes what your keyboard means, the way switching EN to a Chinese
input method does. The OS input switcher already exists, and for people who
switch input methods it is muscle memory. Comparable products treat AI as a place
you go: a separate overlay or app (Click to Do, then "Ask Copilot"), an assistant
you summon, or an agent you supervise. Here it is a way of typing you choose.

That sets the limits on autonomy. Claudish runs only on what you type. It never
acts unprompted, watches the screen, or decides what you should do next. Every
change goes through the input method's contract: you compose, you see what it
becomes, and you accept or discard it. An agent may do the work behind an
accepted instruction, but each side effect it proposes is another explicit
choice. Restraint is the product, not a missing feature.

The proof that matters is not that an IME can call an agent. Many interfaces
can. It is that doing so feels as ordinary as switching input languages: no new
window, no new habit, the same keys. G18 is accepted on that basis (below).

### Principle: autocomplete is the habit

Agents may be why someone installs Claudish; autocomplete is why they keep it. It
has to cost nothing when it is wrong. So continue mode does not hold your words
back at all: they go into the app as you type, and the only uncommitted thing is
the suggestion after the caret. Tab takes it, typing ignores it, Esc dismisses
it, and with nothing offered Tab, Enter, and the arrows are the app's, so forms
and editors keep their keys. A focus change drops only the suggestion. (IBus
discards a commit made during focus-out, so a suggestion inside the composition
would either lose your words or commit text you never accepted; the container
test caught it.)

### Principle: candidates, not one answer

A CJK input method is not expected to guess right the first time. You type a
phonetic sequence, it offers several readings, context ranks them, and you pick
one with a number key and commit it. This happens thousands of times a day,
mostly without thought. The interaction is built around ambiguity.

Claudish generalizes the candidate list from *what you meant to say* to *what you
meant to do*:

| A traditional IME | Claudish |
| --- | --- |
| a phonetic composition | an instruction in plain words |
| character candidates | text, command, or action candidates |
| ranking by context | the model's reading of your context |
| pick with a number or Space | pick, which also approves that operation |
| commit characters | commit text, or run the chosen action |
| cancel the composition | discard every proposal |

So a model's uncertainty becomes a short list, not one confident guess: *"tell the
team it's delayed"* might offer a terse Slack line, a fuller email paragraph, and
a status-page update. Each candidate carries a short legend (what it is, or what
it will do, such as "runs `git push` in ~/claudish"), and the legend matters more
than any paragraph of explanation. This is not a concession to unreliable models.
It is an interaction people already know, and the agent does not have to pretend
it knows.

Picking a candidate approves that candidate, not everything it leads to. If an
agent finds a destructive or outgoing step halfway through, that step comes back
as a new choice (see Safety under G18). Rewrite and continue benefit too: two or
three readings, with 1–3 to pick and Tab for the first (G27).

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

## Supported text boxes (G20)

The future of this integration is simple. Type in a *supported* text box, and
Claudish reads its context and an agent works for you; anywhere else, it is an
input method. Instead of shipping an app per workflow and competing with every
other app's assistant, Claudish sits underneath all of them and grows by
**context providers**: which app or field this is, and what it can read there.

- **Identify:** adapters report the focused app. IBus gives
  `focus_in_id(client)`, as "im module:program"; IMK gives the client's
  `bundleIdentifier`; TSF gives the foreground process. Next comes the field
  as well: IBus content purpose and hints, the window title, the browser URL
  (through accessibility APIs or a small browser extension), and the terminal
  working directory (through the `claudish fix` shell hook).
- **Bind:** profile `bindings` map app patterns to context providers. In time, a
  binding should also choose the default mode, such as instruct in a terminal
  prompt, and its own templates.
- **Read:** providers are files, commands, and MCP servers today. A community
  catalogue of providers per app (GitHub in browsers, Jira, terminals, IDE
  commit boxes, mail composers) is how support grows.
- **Show:** every result lists what was consulted.

### Apps publish MCP; the input method reads it

The integration runs the other way from today's assistants. An app does not
embed an assistant; it **publishes** what it knows over MCP, such as the open
file, the selection, diagnostics, the PR under review, or the ticket you are
answering. Claudish is the client that reads all of them. Type in VS Code, and
the IME sees what VS Code publishes; type in the browser, and it sees what the
web app or its extension publishes. Claude, GPT, and local models become
providers behind your keyboard instead of destination apps that each try to
connect to everything. Longer conversations and approvals can go in a
companion panel, while the caret remains where results land.

What Claudish needs for this is a binding (app → MCP server) and an MCP client
that can reach the server: stdio for servers it starts, and streamable HTTP or
SSE for apps that publish on a local socket (headers from environment
variables, never stored). App-specific internal channels, such as an IDE
extension's private socket, are not targets; published MCP endpoints are.

### Scenario: the address bar

The address bar is a text box too. With a browser MCP server configured
(imported from an existing Claude setup by G24 and bound to the browser), switch
to instruct and type into the omnibox: *"find the cheapest flight to Oslo next
Friday and open it"*. Enter sends it; the agent drives the browser through MCP
tools; questions such as *"Allow navigating to example.com?"* appear as a
candidate list; the result is the page you asked for, not a chat transcript. No
side panel, no extension UI, no separate assistant app: integration follows from
what is configured, and the text box you were already using is the interface. This
needs G17 (instruct may call tools), G18 (sessions and choices), and G24 (MCP
import and bindings); each must keep tool calls visible and side effects
confirmed.

### The composition is a command buffer; commit is the authorization boundary

An input method already separates *composing* from *committing*: nothing reaches
the app until you accept a candidate. Instruct mode extends that from language
conversion (pinyin → characters) to intent conversion (an instruction → an
operation). A composed instruction can end in text committed at the caret, in
an action the agent runs once you approve it (with nothing committed), or in
both: the action, plus a short confirmation inserted. Where you type is a
routing hint (a terminal suggests a command, an address bar navigation, a mail
composer a reply), not a limit on what the instruction may touch. Approval must
say what will happen, where, and with what permissions; destructive or outgoing
actions need their own explicit choice (see Safety above).

### Context, best source first

Supported text boxes are a progressive enhancement, never a prerequisite:

1. **The app's MCP server:** structured, reliable, published by the app.
2. **The OS:** focused app and field, window title, surrounding text and
   selection (IBus surrounding text, TSF, accessibility APIs).
3. **A picture of the focused window:** the universal fallback for apps that
   publish nothing, for a vision-capable backend. Only on an explicit request
   (a key or an instruction), visibly indicated, limited to the focused window,
   never for secure fields, and labelled as hosted when the backend is.
4. **The text alone:** what you typed and what the field exposes.

## Onboarding (G19)

### The pathway: nothing to learn on day one

Switching from en_US to cd_AI changes nothing you have to learn. Continue, where
an installed input method starts, types exactly what you type; a suggestion
appears in grey after a pause, and you can leave it there forever without
pressing Tab. Then, at your own pace, you find F7: instruct (ask for something)
and rewrite (polish your words). The demo leads with rewrite because it is the
pitch; the installed input method leads with continue because it is the habit.
Changes must keep this pathway: continue never holds your words, never takes a
key it does not need, and never asks for attention.

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
