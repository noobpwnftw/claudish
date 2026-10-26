# One request, one answer

How cd_AI answers what you do at the caret. What you see is [design.md](design.md).

Owner, 2026-10-23: "we know the window this was sent, we know what mode it is in, and we know what
MCP is available to use given the configs and all, now we provide this to a model and the model
acts with: either an autocomplete, a rewrite, a text that goes into the place of the caret, or a
question to the user presented as is."

## The request: three things we know

1. **The text box** (`claudish/turn.py`, `Box`), rendered once, the same way for every model:
   - the app and the box's kind (prose, terminal, URL, email, number, ...), stated as a fact
     ("what you write here is a command line, run when the user presses Enter");
   - the text around the caret (about 1,500 characters before and 500 after, the caret marked),
     the selection, the box's length; the rest of the box is a tool (`textbox.read`,
     `textbox.search`), read live at the moment of the call;
   - observations: the profile's context providers and the app's bindings (files, commands, MCP
     resources); a terminal's screen, read through the accessibility APIs on Tab or Shift+Enter in
     compose (the last lines); a picture of the window on F8. Every result lists what was
     consulted.
2. **What you did:** the mode and the key (a pause in continue, Tab or Shift+Enter in compose, an answer
   to a question), and the text box's conversation so far.
3. **What is available:** the tools the configuration allows there: the profile's MCP servers
   under their trust and deny policy, and Claudish's own (the text box, a helper such as Claude
   Code), each read-only, writing, or destructive.

## The answer: four actions

| Action | Where it goes | Asked by |
| --- | --- | --- |
| **complete** | after the caret, gray; Tab takes it | a pause in continue |
| **replace** | the rewrite in the panel; Tab puts it in | Tab in compose |
| **insert** | drafts in the panel; ↑ ↓ choose, Tab inserts | Shift+Enter in compose |
| **ask** | a question with choices, or an answer to read, shown as is; the answer goes back to the model | an instruction, when it needs you |

Side effects happen only through tools, and a tool that writes or acts goes through **ask** first
unless the configuration trusts it. Handing a task to a helper is such a tool ("Send this task to
claude?", No first): it opens the helper with a note (the task and what was observed), and the
turn ends as **done**. Whatever is inserted obeys the box's kind, in one place: a terminal gets
one physical line (a newline at a prompt is a Return).

## One loop

Every intent runs the same loop (`Rewriter.answer`): describe the request, call the model with the
tools that intent may use, run tool calls (asking when policy says so), return one action. The
intents differ only in budget: continue gets no tools and a few tokens (it runs at every pause),
a rewrite no tools, an instruction all the tools and the conversation. An agent CLI (Claude Code
over stream-json) is the loop's other implementation: it gets the same request, and its
permission prompts and its own questions become **ask**.

## The answer's shape

Every mode answers `{"drafts": [...]}`: one draft, or two or three versions when an instruction asks
for several (`claudish/shapes.py`). A backend that takes a schema is held to it, and the answer is
read as data: an OpenAI-compatible server through `response_format` (llama.cpp compiles it to a
grammar), the Claude API through `output_config.format`, Claude Code through `--json-schema`. On an
OpenAI-compatible server an instruction's tool calls are steps of the same schema, `{"call": tool,
"arguments": {...}}`, each tool with its own argument schema, so the server enforces them where a
model's native tool-call format may not be; the system prompt lists what each tool does
(`box.steps`). A backend without a schema (a command, Codex, a server that refuses
`response_format`) answers in plain text, read through `claudish/quirks.py`, the one place that
knows how models wrap an answer.

## A conversation per text box

A conversation belongs to a text box (IBus's input context, TSF's document, IMK's client), and each
instruction is a turn in it. It keeps every instruction, the drafts offered and the one taken, each
tool call and result (large results trimmed), your answers, and approvals given for the session;
each turn sends the box fresh, so your edits are what the model sees. An agent keeps one process
per conversation, resumed by session id if it ends. A conversation ends when the text box goes
away or after 30 idle minutes.

## The tool policy

| Class | From | What happens |
| --- | --- | --- |
| read | `readOnlyHint`, or listed in `trust` | runs; listed in what was consulted |
| write | everything else | asks: Deny first, Allow, Allow for this conversation |
| destructive | `destructiveHint` | asks every time; never for the conversation; the question says it is destructive |
| denied | listed in `deny` | never offered to the model |

A question shows what will actually happen (the tool and its key arguments), not a paraphrase.
Typed words refuse it with your words as the reason. The same policy answers an agent's
permission requests.

## Bounds

- **Budgets:** rounds of tool calls (4 by default) and wall time (60 s); when one runs out, the
  model gets one last turn without tools.
- **Esc** stops the turn.
- **Drafts after tools:** tools run once; the final answer can be sampled again over the same
  results, so an instruction that looked things up still offers up to three drafts.

## Context, best source first

1. The app's MCP server: structured, published by the app (apps publish; Claudish reads).
2. The OS: the focused app and field, the text around the caret and the selection.
3. What a screen reader sees: the accessibility APIs (AT-SPI, UI Automation, AX) identify the
   focused element and expose its text with nothing installed in the app; for terminals this is
   the screen (GNOME Terminal, Windows Terminal and the console, Terminal.app). macOS needs the
   Accessibility permission for the service's Python; Linux needs the accessibility bus.
4. A picture of the focused window, on request (F8), for a vision-capable backend.
5. The text alone.

In a terminal the model sees the screen and your words ("fix") and does one of three things, each
with a shape at the caret: the command itself (a draft at the prompt; running it is your Enter),
a question when your intent is unclear ("did you mean `git status`?"), or an offer to hand the work
to a helper.

## Backends

OpenAI-compatible servers (llama.cpp, vLLM, Ollama: `tools` and `tool_calls`), Claude through the
official SDK (client-side tools), and agent CLIs (Claude Code over stream-json).
