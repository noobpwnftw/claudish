# One request, one answer

Owner, 2026-10-23: "we know the window this was sent, we know what mode it is
in, and we know what MCP is available to use given the configs and all, now we
provide this to a model and the model acts with: either an autocomplete, a
rewrite, a text that goes into the place of the caret, or a question to the user
presented as is."

This page is that architecture, and the plan to move the code to it. Until now
each situation grew its own path (a terminal template, a screen placed in the
turn, one-line drafts, a handoff tool only in terminals); each was a special
case of the same thing.

## The request: three things we know

1. **The text box.** What the adapters and the observers report, rendered once,
   the same way for every model call:
   - the app, and the box's kind (prose, terminal, URL, email, number, ...);
   - the text before and after the caret, and the selection;
   - observations made on request: a terminal's screen (accessibility), a
     picture of the window (F8), the profile's context providers and the app's
     bindings (files, commands, MCP resources);
   - what the kind implies, stated as a fact: "what you write here is a command
     line, run when the user presses Enter".
2. **What the user did.** The mode and the key: a pause in continue, Tab in
   compose (rewrite your words, or a selection), Enter in compose (an
   instruction), an answer to a question; and the text box's conversation so far.
3. **What is available.** The tools the configuration allows here: the
   profile's MCP servers under their trust and deny policy, Claudish's own
   (the text box's full text, a helper such as Claude Code), each marked
   read-only, writing, or destructive.

## The answer: four actions

The model answers with exactly one of:

| Action | Where it goes | Asked by |
| --- | --- | --- |
| **complete** | after the caret, grey; Tab takes it | a pause in continue |
| **replace** | in place of your words or the selection; Tab keeps it | Tab in compose |
| **insert** | drafts at the caret, 1–3 to pick | Enter in compose |
| **ask** | a question with choices, shown as is; the answer goes back to the model | any instruction, when it needs you |

Side effects happen only through tools, and a tool that writes or acts goes
through **ask** first unless the configuration trusts it. Handing a task to
Claude Code is such a tool: after "Send this task to claude? 1 Yes 2 No", it
opens the helper with a note (the task and what was observed), in any text box.
In a terminal the model can also simply **insert** `claude "…"` as the command,
because the box says what goes there; no special case either way.

Whatever is inserted obeys the box's kind, centrally: a terminal gets one
physical line (a newline at a prompt is a Return), a password field gets
nothing.

## One loop

Every intent runs the same loop: describe the request, call the model with the
tools that intent may use, handle tool calls (asking when policy says so),
return one action. The intents differ only in budget: continue gets no tools
and a few tokens (it runs at every pause), rewrite no tools, an instruction all
the tools and the conversation. An agent CLI (Claude Code over stream-json) is
another implementation of the same loop: it receives the same request and its
permission prompts become **ask**.

## What changes in the code

| Today | Becomes |
| --- | --- |
| `modes.py` templates per mode, `TERMINAL_SYSTEM`, tone templates | one system prompt: Claudish's role, the tone (a voice line), the action asked for; templates stay overridable per action |
| `describe`, `window`, `terminal`, `in_terminal`, `screen_note` (conversation.py) | one `TextBox` description: kind facts, the window around the caret, observations (fenced as material, not instructions), what was consulted |
| `Rewriter.terminal`, screen reads in `rewrite` and `make_driver` | observers run by the request builder, by kind and intent (a terminal's screen for compose, never for continue) |
| `Rewriter.rewrite` (single shot) and `ModelDriver.run` (tools, conversation) | one loop; rewrite and continue are turns without tools |
| result candidates, session events, `one_line` in two places | one response type (complete, replace, insert, ask) and one place that applies the box's constraints |
| the parked handoff branch (`agent/handoff`: a terminal-only tool and a key) | a helper tool among the others, behind **ask**, anywhere |

The adapters change little: they already send the box (app, kind, text around
the caret) and the key, and already render a candidate, a list, or a question.

## Where it stands

Steps 1–3 are done (2026-10-23): `claudish/turn.py` holds the text box (`Box`:
kind, app, the text around the caret, observations, constraints), the observers,
and the system prompt; `Rewriter.answer` is the one loop for `/suggest` and for
instruction sessions alike; the terminal template, `in_terminal`, and the
per-path screen reads are gone. Measured against the special-cased version:
fidelity 38/41 (unchanged); the terminal set, Qwen3 30B 20/23 fixed
(unchanged), Qwen2.5 1.5B 7/23 fixed with 6/7 legitimate commands left alone
and 1 harmful (was 2/23, 1/7, 6 harmful). The general rules (voice only for
prose, observations next to the request, the kind stated as a fact) did better
than the hand-made terminal template.

## Order of work

Each step keeps the gate green and the prompts measured (the fidelity eval and
the terminal eval must not get worse):

1. `TextBox` and one description renderer; port every path to it with the same
   prompt text.
2. One system prompt per action, with the tone as a line; terminal facts come
   from the box kind (re-run the terminal eval: 20/23 on Qwen3 30B today).
3. One loop for all intents; `Rewriter.rewrite` and `ModelDriver` merge.
4. The typed response, and the box constraints applied in one place.
5. Helpers as tools behind **ask** (G39), in any text box.
