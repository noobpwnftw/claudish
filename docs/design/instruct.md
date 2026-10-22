# Design: how instruct calls models and tools

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

## One pipeline: every sent instruction is a session

```
instruction ─▶ assemble ─▶ driver ─▶ events ─▶ input method
                 │            │                    │
   template, examples,   model driver:        progress (each tool call)
   profile context,      Claudish runs        partial draft
   app bindings,         the loop             question (1–9, or your words)
   text around caret,    ─ or ─               result: readings to pick
   window picture (F8)   agent driver:        error
                         an agent CLI runs
                         it; Claudish hosts
```

1. **Assemble.** The mode's template and examples, the profile's context, the
   bindings for the focused app, the text around the caret, the window picture
   if you pressed F8, and the instruction itself.
2. **Drive.** Two kinds of driver behind one interface:
   - **Model driver:** Claudish runs the loop. It sends the conversation and the
     offered tools to the backend; for each tool call it applies the policy below,
     runs the tool on its MCP server, appends the result, and asks again, until the
     model answers without a tool call or the budget runs out.
   - **Agent driver:** an agent CLI runs the loop with its own tools; Claudish is
     its host and turns each permission request into a question, through the same
     policy.
3. **Events.** Both drivers emit the same events, so every adapter renders them
   the same way: progress in the status line, questions as a numbered list, the
   result as readings to pick. A plain instruction is a session with no tool
   calls; it returns at once.

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

1. The model driver as a session: progress events for each tool call, and the
   policy with write tools asking through the candidate list (questions already
   render in all three adapters).
2. Readings after tools.
3. Claude's tool loop (needs credentials to verify).
4. Streaming the final turn as a partial draft.

Each step keeps today's behavior for profiles without tools.
