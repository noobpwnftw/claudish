# Design: how instruct calls models and tools

Scope: each instruction is one turn at the caret; the conversation is only the
context carried between turns in a text box, never a chat surface
([interaction.md](interaction.md#scope-an-input-method-not-a-chat-app)).

Instruct is the AI integration path: an instruction typed at the caret becomes model
calls, tool calls, and finally text you choose to insert. Today it has three
separate paths that behave differently. This page makes them one pipeline.

## Today

| Path | Who runs the loop | Tools | Side effects | What the input method sees |
| --- | --- | --- | --- | --- |
| Plain instruct | one model call (n readings) | none | none | final candidates |
| `tools` (G17) | Claudish, OpenAI-compatible backends only | read-only MCP tools, called automatically | never offered | the final text; calls listed afterwards |
| `session_command` (G18) | an agent CLI (Claude Code) | the agent's own | each permission request becomes a choice | progress, partial draft, questions, result |

The gap: when Claudish runs the loop itself, it cannot ask you anything, so
side-effecting tools are simply excluded and you see nothing until the end. Only
an external agent gets the interactive treatment.

## One pipeline, one conversation per text box

A fresh session for every instruction would throw away what makes multi-turn work
useful: earlier instructions and what was offered, tool calls and their results,
which draft you took, and standing approvals. And, as continue showed, a model
without the text box is guessing. So a conversation belongs to a **text box**,
and each instruction is a turn in it.

```
text box ─▶ conversation ─▶ turn: assemble ─▶ driver ─▶ events ─▶ input method
              │  (kept)                │            │
   instructions, drafts offered     the text box   model driver: Claudish runs
   and taken, tool calls and        as it is now,  the loop
   results, answers, approvals      caret marked   ─ or ─
                                                   agent driver: a long-lived
                                                   agent process per conversation
```

### Identity: the text box

Each platform already gives an input method one context per text field: IBus
creates an engine instance per input context, TSF has a context per document, and
IMK has a client per field. That is the conversation's key. Switching to another
field switches conversation; coming back resumes it.

### What a conversation keeps, and what it sends fresh

- **Kept:** every instruction; the drafts offered and the one you took; each tool
  call with its result (large results trimmed); your answers; approvals given "for
  this session". Long conversations are compacted (older turns summarized), never
  silently dropped.
- **Fresh every turn:** a window around the caret, not the whole text box (see
  below), plus the profile's context, the app's bindings, and the window picture if
  you pressed F8. If you edited the inserted draft, the model sees your edits, not
  its own old text.

### The text box: a window, plus retrieval

Sending the whole text box every turn would paste a long email, document, or code
file into every call. Instead:

- **Always sent:** about 1,500 characters before the caret and 500 after, with the
  caret marked; the selection, if any; the box's length and the app. Short text
  boxes (most of them) fit whole, and a model always has enough to stay coherent,
  even one that never calls a tool.
- **Retrieved when needed:** the full text box is a tool: `textbox.read` (a range),
  `textbox.search` (lexical first; embeddings if it earns them), and
  `textbox.selection`. The model calls it when the instruction needs it
  ("summarize this thread", "fix the second paragraph"). A read is a read-only tool
  under the policy, listed in "consulted", and kept in the conversation like any
  tool result, so later turns need not read it again.
- **Live, not a snapshot:** retrieval reads the text box as it is at the moment of
  the call (adapters send the current text with each request; the service holds
  the latest), so edits between turns are what it finds.
- **For agents:** Claudish serves the text box as an MCP server to the
  conversation's agent process, so an agent such as Claude Code reads the current
  document with tools like any other MCP source: the "apps publish MCP" idea, with
  Claudish as the publisher.

### Agents keep their own state

The agent driver keeps **one agent process per conversation** alive between
instructions (stream-json accepts more user turns), so an agent such as Claude
Code keeps its files read, its plan, and its tool results. If the process ends,
the next turn resumes it by session id (`--resume`).

### When a conversation ends

- the text box goes away (its input context is destroyed);
- it has been idle for a while (30 minutes by default);
- nothing else: no slash commands or history to manage (scope: an input method,
  not a chat app); the idle timeout and the text box's lifetime cover it.

Conversations live only in the service's memory, never on disk, and are dropped
when they end.

### Each turn

1. **Assemble:** the mode's template, the conversation so far, the window around
   the caret, context and picture, then the instruction; the rest of the text box
   is a tool.
2. **Drive:** one of two drivers behind one interface:
   - **Model driver:** Claudish runs the loop. It sends the conversation and the
     offered tools to the backend; for each tool call it applies the policy below,
     runs the tool on its MCP server, appends the result (to the conversation, so
     later turns have it), and asks again, until the model answers without a tool
     call or the budget runs out.
   - **Agent driver:** the conversation's agent process runs the loop with its own
     tools; Claudish is its host and turns each permission request into a question,
     through the same policy.
3. **Events:** both drivers emit the same events, so every adapter renders them the
   same way: progress in the status line, questions as a numbered list, the result
   as readings to pick.

## The tool policy (one policy, both drivers)

Each tool gets a class from its MCP annotations and the profile:

| Class | From | What happens |
| --- | --- | --- |
| read | `readOnlyHint`, or listed in `trust` | runs; listed in "consulted" |
| write | everything else | asks: **1** Allow, **2** Deny, **3** Allow for this session |
| destructive | `destructiveHint` | asks every time; no "for this session"; the legend says it is destructive |
| denied | listed in `deny` | never offered to the model |

A question's legend shows what will actually happen: the tool and its key
arguments (`github.create_issue: "Flaky upload test" in noobpwnftw/claudish`), not
a paraphrase. Typing words instead of a number denies the call with your words as
the reason, so the model can adjust ("not that repo, use the fork").

The same policy answers an agent's permission requests: read-only agent tools can
be allowed by policy instead of interrupting you, and the rest become questions.

## Bounds and trust

- **Budgets:** rounds of tool calls (4 by default), wall time (60 s), and, for
  hosted backends, tokens. When a budget runs out the model gets one last turn
  without tools: answer with what you have.
- **Tool results are data, not instructions.** Text from a tool, a web page, or the
  app's context can say anything; it can never approve a call. Every write still
  needs your answer, and the legend shows the real arguments.
- **Esc** at any point stops the session and keeps your words; nothing a session
  did is inserted until you pick it.

## Readings after tools

Tools run once; the final answer can then be sampled several times over the same
results, so an instruction that looked things up still offers readings 1–3, at
the cost of the last turn only.

## Backends

- **OpenAI-compatible** (llama.cpp, vLLM, Ollama): `tools` and `tool_calls`. Done
  for read-only tools.
- **Claude:** the same loop with the SDK's client-side tools (`tool_use` and
  `tool_result` blocks). Local stdio MCP servers stay client-side; remote ones
  could use the API's MCP connector later. Needs a live check with credentials.
- **Agent CLIs:** Claude Code over stream-json (done); others through the same
  agent driver.

## Order of work

1. **Done:** conversations per text box in the service (identity from the adapters,
   kept turns, the window around the caret each turn, idle timeout), with
   the model driver as its first driver: progress for each tool call, and the
   policy with write tools asking through the candidate list. The agent driver
   keeps one process per conversation: Esc interrupts a turn rather than killing
   the agent, an exited agent is resumed by session id, and the agent exits with
   its conversation.
   **Done:** the text box as retrieval. The window around the caret is sent each
   turn; when the text box is longer, the model driver offers `textbox.read` and
   `textbox.search` (Claudish's own read-only tools, no MCP SDK needed), and an
   agent gets the same two tools from `claudish textbox-mcp`, an MCP server
   Claudish configures for it with `--mcp-config`. The server reads through the
   service with the conversation's token, so no other local process can read the
   text box; the agent's reads are allowed by policy, without a question.
   Selection is not sent by the adapters yet.
2. Readings after tools.
3. Claude's tool loop (needs credentials to verify).
4. Streaming the final turn as a partial draft.

Each step keeps today's behavior for profiles without tools.
