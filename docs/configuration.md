# Configure

Models, profiles, context, MCP servers, tools, window pictures, and agent sessions.

## Backends

Claudish supplies the plumbing: the input method, its templates, and the
service between them. The model is your choice, and how well it follows the
template depends on that model. `benchmarks/evaluate.py` measures any backend
on the same cases.

Use any OpenAI-compatible server and any model, such as llama.cpp, vLLM, Ollama,
LM Studio, or a hosted endpoint:

```sh
python -m claudish serve --backend openai --model-url http://127.0.0.1:11434 --model qwen2.5:7b
# A remote endpoint, with a key read from an environment variable that you name:
python -m claudish serve --backend openai --model-url https://api.example.com \
    --model some-model --api-key-env EXAMPLE_API_KEY --timeout 10
```

Or use Claude through the official SDK. It is an optional dependency. The
credentials are yours: set `ANTHROPIC_API_KEY`, or run `ant auth login`.

```sh
pip install "claudish-ime[claude]"
python -m claudish serve --backend claude                     # claude-opus-5-5
python -m claudish serve --backend claude --claude-model claude-haiku-5-5
```

The Claude backend runs one request at a time, uses low effort, and turns on
server-side refusal fallbacks (except on Haiku, which has none). It never
offers a declined or truncated rewrite; your wording stays. Typed text goes
only where you point the service. A non-loopback `--model-url` and the Claude
backend are reported as `"hosted": true` in `/health`, and the browser demo
labels them as hosted. Local inference remains the default.

Change what the model is told with a templates file, for any backend (see
[Templates](#templates)): `claudish serve --templates FILE`, or a profile's
`"templates"`.

### Supported text boxes

The input method knows which app has focus. On Linux, IBus reports the program
(`gtk3-im:firefox` arrives as `firefox`). On macOS it is the bundle identifier
(`com.apple.Terminal`); on Windows, the program file (`notepad.exe`).
`bindings` attach context to apps:

```json
{"profiles": {"work": {"backend": "claude", "bindings": [
  {"app": "firefox*", "context": [{"type": "mcp", "name": "PR diff", "command": ["github-mcp-server", "stdio"],
                                   "tool": "get_pull_request_diff", "arguments": {"owner": "me", "repo": "app", "pullNumber": 42}}]},
  {"app": "com.apple.Terminal", "context": [{"type": "command", "command": ["git", "status", "--short"]}]}
]}}}
```

In a bound app, Claudish reads that context and the model or agent works with
it. Everywhere else it is a plain input method. Patterns are case-insensitive
globs. Every response lists what was `consulted`, so it is always visible what
the AI read. Support grows by adding context providers per app, not by
installing another app.

A binding can also say **which AI answers** there, by naming another profile of
the same file: its backend, tone, tools, and helper answer for that app.

```json
{"profile": "local", "profiles": {
  "local": {"backend": "llama", "bindings": [
    {"app": "slack*", "profile": "plain"},
    {"app": "firefox*", "profile": "claude"},
    {"app": "gnome-terminal-server", "profile": "agent"}]},
  "plain": {"backend": "llama", "tone": "plain"},
  "claude": {"backend": "claude"},
  "agent": {"backend": "llama", "helper": ["claude", "{prompt}"]}}}
```

A mode can name the profile that answers it, too: continue runs at every pause
and wants a small, fast model; an instruction is sent on purpose and can wait
for a strong one.

```json
{"profiles": {"local": {"backend": "llama", "modes": {
  "continue": {"profile": "tiny"}, "instruct": {"profile": "claude"}}}}}
```

The app's binding chooses first, then that profile's choice for the mode. The
service's own profile (`claudish serve --profile`, or the file's `"profile"`)
holds the bindings; other profiles are loaded when they are first needed, and a
hosted one is announced when it is.

### An agent CLI as the backend

An agent CLI is a text box and Enter, and an input method is a text box in every
app. With `"backend": "command"`, the input method becomes that CLI's text box.
Claudish sends the mode's instructions, the profile's context, and your text on
stdin; the command's output becomes the candidate, which you accept with Tab:

```json
{"profiles": {"agent": {"backend": "command", "timeout": 120,
                        "command": ["claude", "-p", "--output-format", "text"]}}}
```

Any CLI that reads a prompt on stdin works: `claude -p`, `ollama run MODEL`,
`llm`, or your own script. The command comes only from your config, runs without a
shell, and never sees your text as arguments. Tool permissions are the CLI's
own; for example, Claude Code's `--allowedTools` in the command list. Agents are
slow, so the profile's `timeout` applies (`/health` reports it), and typing is
never blocked while one works. These profiles are reported as hosted unless
the profile sets `"hosted": false`.

Measured on the Spark with Claude Code 2.1.306: an instruct request ("thank
Priya for fixing the flaky CI job, it saved the release") returned a finished,
em-dashed thank-you note in 4.5 s.

### Profiles

Instead of passing flags, declare your backends once in
`~/.config/claudish/config.json` (or `$XDG_CONFIG_HOME/claudish/config.json`, or
pass `--config FILE`):

```json
{"profile": "local",
 "profiles": {
   "local":  {"backend": "llama"},
   "ollama": {"backend": "openai", "model_url": "http://127.0.0.1:11434", "model": "qwen2.5:7b",
              "templates": "grand.json"},
   "remote": {"backend": "openai", "model_url": "https://api.example.com", "model": "some-model",
              "api_key_env": "EXAMPLE_API_KEY", "timeout": 10},
   "claude": {"backend": "claude", "claude_model": "claude-opus-5-5"}
 }}
```

`python -m claudish serve` uses the file's `"profile"`. `--profile claude`
picks another, and any flag overrides the profile's value. A template path in a
profile is relative to the config file. Keys are never stored in the file: name
an environment variable with `api_key_env`. Unknown keys, a literal `api_key`,
and wrong types are rejected at startup. `/health` reports the active profile.

### Window pictures

For apps that publish nothing Claudish can read, an instruction can carry a
picture of the window you are typing in. In compose, press **F8** before
Enter: the hint shows "instruct + window picture", and the service captures the
focused window once, sends it with that one instruction, and lists it in
"consulted". Nothing is captured without F8, F8 never carries over to the next
instruction, password fields never reach Claudish, and the picture is not stored
or logged. With a hosted backend it goes to that service, as your text does.

- **Capture:** Windows uses PrintWindow (built in). Linux X11 needs `xprop` and
  ImageMagick (`sudo apt install x11-utils imagemagick`). On Wayland or macOS,
  set the profile's `"look_command"` to a program that writes a PNG of the
  focused window to stdout, such as a `grim` or `screencapture` wrapper.
- **Backends:** `claude` and any OpenAI-compatible server with a vision model.
  For llama.cpp, start a vision model with its projector, for example
  [Qwen2.5-VL-3B](https://huggingface.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF):
  `llama-server -m Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf --mmproj
  mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf -c 8192`. The `command` backend refuses.

Verified with a real capture in both places. On Windows 11 ARM64, a Notepad
invoice was captured with PrintWindow and sent to Qwen2.5-VL-3B (Q4_K_M) on the
Spark GPU; "what is the amount due here?" returned "The amount due is 1,250.00
EUR." in 0.18 s. On X11, the desktop test captures a GTK window with ImageMagick.

### Context

A profile can attach reference context that the model sees with your text: a
file such as a style guide or glossary, or any local command's output. For
example, the diff of the branch whose PR description you are writing:

```json
{"profiles": {"pr": {"backend": "claude", "context": [
  {"type": "command", "name": "branch diff", "command": ["git", "-C", "~/src/app", "diff", "main...HEAD"], "ttl": 60},
  {"type": "file", "path": "~/notes/style.md"}
], "max_context_chars": 6000}}}
```

Commands run exactly as configured, without a shell, and only from your config
file; requests cannot add them. Results are cached for `ttl` seconds (default
30). A failing or slow provider (`timeout`, default 5 s) is skipped, never
blocking a rewrite. Context goes into the system prompt, ahead of your text, so a
local llama.cpp server reuses its prompt cache while you type. Adapters may also
send the text around the caret as `before`/`after` in `/suggest`. Context goes
to the profile's backend, so with a hosted backend it leaves the machine like
your text does.

MCP servers can supply context too (`pip install "claudish-ime[mcp]"`). Claudish
starts the configured stdio server, calls one tool or reads one resource, and
caches the text:

```json
{"type": "mcp", "name": "PR diff", "command": ["github-mcp-server", "stdio"],
 "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "$GITHUB_TOKEN"},
 "tool": "get_pull_request_diff", "arguments": {"owner": "me", "repo": "app", "pullNumber": 42},
 "ttl": 120, "timeout": 15}
```

`"$NAME"` values in `env` are read from your environment, so tokens stay out of
the config file. Use `"resource": "uri"` instead of `"tool"` to read a resource.

Already using MCP servers with Claude? Bring them along:

```sh
python -m claudish mcp import            # from Claude Desktop, Claude Code (~/.claude.json), and ./.mcp.json
python -m claudish mcp list              # connect to each server; show its tools and resources
python -m claudish context test --app firefox --show   # what a binding would read in that app
```

Imported servers land under `"mcp_servers"` in your config and are used by name:
`{"type": "mcp", "server": "github", "tool": "...", "arguments": {...}}`. Secrets
are never copied: every `env` and header value becomes a `$NAME` reference, and
`import` lists the variables to set.

Apps that publish MCP on a local socket are read with `url` instead of
`command`: streamable HTTP by default, or `"transport": "sse"`. Headers may use
`"$NAME"` values from your environment:

```json
{"type": "mcp", "name": "editor", "url": "http://127.0.0.1:3920/mcp",
 "headers": {"Authorization": "Bearer $EDITOR_MCP_TOKEN"}, "tool": "get_selection"}
```

Paired with a binding, this lets an app hand its context to the input method
without knowing Claudish exists.

For a deterministic demo without a model, use `python -m claudish serve
--backend rules`. That mode performs simple word substitutions and identifies
itself as `rules` in API responses. It does not perform neural rewriting.

### Tools: instructions that look things up

Context is read before the model starts. Tools go further: an instruction may
*call* MCP tools while it works, then draft from what they returned, for example
"tell the team how CI looks on main". Name servers from `mcp_servers` in a
profile:

```json
{"profiles": {"agent": {"backend": "llama", "timeout": 60,
  "tools": ["github", {"server": "notes", "trust": ["pull_request_diff"]}]}}}
```

- Tools the server marks read-only (`readOnlyHint`), and the ones you vouch for
  with `"trust"`, run without asking. Any other tool asks first, in the panel: Deny,
  Allow, Allow for this conversation, with nothing highlighted (the first ↓ lands on
  Deny, so Allow is a deliberate ↓↓ Enter); a tool marked destructive
  (`destructiveHint`) asks every time. Typing words instead denies the call with your
  words as the reason. `"deny": [TOOL, ...]` keeps a tool
  from ever being offered.
- Instructions in the same text box are one **conversation**: later instructions
  see earlier ones, the drafts, and the tool results ("now make it shorter" works).
  The text around the caret goes along fresh each time. A conversation ends when
  its text box goes away or after 30 idle minutes, and lives only in memory.
- Every call appears in "consulted", such as `notes.ci_status(branch="main")`.
- The loop is bounded: at most 4 rounds of calls, and 60 s in all. The result is
  still only a candidate.
- It needs an OpenAI-compatible server whose model calls tools (llama.cpp, whose
  chat templates handle tool calls by default, vLLM, Ollama). On the Spark, Qwen2.5-14B called the right tool and
  drafted from its result ("41 tests have passed… test_upload_retry timed out
  after 30 seconds", 3.1 s), and called none for a haiku. Qwen2.5-1.5B never
  called a tool and wrote around the gap. Claude runs the same loop with the SDK's
  client-side tools, and an agent CLI (`session_command`) uses its own.

### Agent sessions: an agent at the caret

With `"session_command"` in a profile, a sent instruction (Enter in compose)
runs an agent instead of a single model call. Claudish is the agent's host: its
progress and partial draft show in the input method's status line, its
permission questions show in the panel (what would run, in full; Deny first, nothing
highlighted), the questions it asks you
itself (Claude Code's AskUserQuestion) are shown as is with its options to
pick, and its final answer is a candidate like any other. For Claude Code:

```json
{"profiles": {"code": {"backend": "llama",
  "session_command": ["claude", "--print", "--input-format", "stream-json",
    "--output-format", "stream-json", "--verbose", "--include-partial-messages",
    "--permission-prompts", "host"]}}}
```

- *"is my branch clean?"* → `Allow — Bash: git status` / `Deny`: **1** allows that one
  call, **2** denies it (the agent carries on without it), or type a reply and
  press Enter: it denies the call with your words as the reason ("use git diff
  instead"), so the agent can adjust. Nothing runs without
  your choice unless your own Claude Code settings already allow it.
- **Esc** at any point stops the agent's turn and gives you back the instruction to
  refine; Esc again drops it. Editing the instruction stops the turn too.
- **Follow-ups continue the same agent.** Each text box has its own agent
  process, started at the first instruction and kept between them, so "now
  shorten it" or "and the other branch?" builds on the files it read, its plan,
  and its tool results. Esc interrupts the turn but keeps the agent. If the
  process exits, the next instruction resumes its session (`--resume`). The agent
  exits when the text box goes away, after 30 idle minutes, or when the service
  stops. Claudish adds `--session-id` and `--permission-prompt-tool stdio` itself
  (without the latter, Claude Code denies by itself instead of asking you).
- **The agent gets your Claudish setup, not just its own.** The servers named in
  the profile's `tools` are passed to it (`--mcp-config`, with your config's own
  `${VAR}` references, so no secret is written out), under the same policy as the
  model: `deny` tools are never offered (`--disallowedTools`), `trust` tools run
  without asking, the rest ask. The profile's `context` and the app's bindings go
  with each instruction, as they do for the model.
- **The agent sees your text box.** The text around the caret goes with each
  instruction, and with the `[mcp]` extra installed, Claudish gives the agent a
  `textbox` MCP server (read, search) for the rest, so "fix the second paragraph"
  works in a long document. Its reads run without asking; nothing else can read
  the text box. Without an agent, the model driver has the same two tools
  whenever the text box is longer than what it is sent.
- The agent runs with your Claude Code login, settings, and working directory
  (the service's), and its usage counts as yours. A session is limited to five
  minutes and four at a time.
- Status: tested end to end in the Linux desktop container (real IBus and GTK)
  with a scripted agent that speaks Claude Code's stream-json protocol (the
  message shapes come from the Agent SDK's control protocol), plus the PIME smoke
  and the macOS doubles, and live against Claude Code (2.1.308). On Windows (Claudish's
  own PIME) a question shows as it arrives.

### Helpers: handing a task over

An instruction can end in handing the task to an agent such as Claude Code,
from any text box. Set the profile's `"helper"` to its command, with `{prompt}`
(a request to read the handoff note) or `{note}` (the note's path):

```json
{"profiles": {"local": {"backend": "llama", "helper": ["claude", "{prompt}"]}}}
```

The model offers it when a task takes more than an answer at the caret, or
when you ask ("have claude look into why the build fails"), and you are asked
first: "Send this task to claude?", with No first and then Yes. Yes opens the helper in a new
terminal window, on a note with the task and what was observed (a terminal's
screen, redacted), in a file only you can read; nothing is inserted. The note
never goes on a command line. Not offered when the program is not installed or
the command skips the helper's own permission prompts. Needs a backend with
tool calls (llama.cpp, any OpenAI-compatible server, or Claude).

With `{session}` in Claude Code's command, Claudish starts it on a session id it
chose and keeps that in the text box's conversation, so a later "is it done?" in
the same box can read the helper's latest messages from its own transcript
(nothing is sent to it):

```json
{"profiles": {"local": {"helper": ["claude", "--session-id", "{session}", "{prompt}"]}}}
```

Codex is followed the same way, through the session that mentions the handoff
note; any other helper can be followed when a tmux launcher names its window
(`["tmux", "new-window", "-n", "{name}", "{command}"]`): Claudish reads the
window's last lines, redacted like a terminal screen.

Several helpers can be named, each its own tool behind its own question, and a
`"launcher"` says how they open (`{command}` is the helper's command):

```json
{"profiles": {"local": {"helper": {"claude": ["claude", "{prompt}"], "codex": ["codex", "{prompt}"]},
                        "launcher": ["tmux", "new-window", "{command}"]}}}
```

When you ask to understand something ("what does this error mean?"), the model
can show an answer to read instead of text for the box, marked "The model
says", with Tab to insert it or Esc to dismiss it.

The model can also ask you itself, as a question with choices ("Did you mean
git status?"); your answer goes back to it.

### Tone

Claudish's voice (polished, slightly verbose, fond of em dashes) is the default
and the point. A profile can speak in another one:

```json
{"profiles": {"work": {"backend": "llama", "tone": "plain and concise"}}}
```

Two tones are named: `"plain"` (plain, natural English) and `"fix"`, where Tab
corrects spelling, typos, grammar, and capitals and keeps your words, their
order, and your voice (for dyslexia, a second language, or a phone keyboard);
continue and instruct are plain then. Any other words work too ("warm and
friendly", "formal British"). The tone replaces the voice in the rewrite,
continue, and instruct templates, and Claudish's own examples, which teach its
voice, are left out. `claudish setup --tone fix` sets it for you. A mode's own
`"system"` in the profile's templates wins over the tone. Instructions typed in a
terminal always get a command line.

## Modes

Every request names a mode, and every mode only offers a candidate, which you
accept with Tab or ignore:

| Mode | You type | The candidate |
| --- | --- | --- |
| `rewrite` (default) | a phrase | the phrase, rewritten in house style |
| `continue` | the start of a sentence | your text plus the next few words |
| `instruct` | an instruction, such as "decline politely, propose Thursday" | the text itself, written using the profile's context |

The browser demo has a mode switch. Adapters send `"mode"` in `/suggest`, and
`/health` lists the modes. A profile's templates can change any mode, or add one
of its own; its `"modes"` says only which profile answers a mode (above).

## Templates

Every word cd_AI says to a model is in
[`claudish/templates.json`](../claudish/templates.json): each mode's `system`
prompt, the `plain` one for boxes that are not prose (a terminal, a URL, a
number), `examples` as `[input, answer]` pairs, a `frame` around your text
(`{text}`), `max_tokens` and `candidates` (how many readings to offer, 1 to 5);
the tones; and the wording about the text box (`box`). A templates file has the
same shape and names only what it changes, mode by mode and key by key:

```json
{"modes": {"rewrite": {"system": "Rewrite, do not reply. Keep names and numbers exactly. Use an em dash.",
                       "examples": [["the server is down", "The server is down—currently, and regrettably, unreachable."]]},
           "instruct": {"max_tokens": 900},
           "haiku": {"system": "Answer in a haiku.", "max_tokens": 60}}}
```

Name it in a profile (`"templates": "words.json"`, relative to the config file)
or pass `claudish serve --templates words.json`. A mode's own `system` is used
as written in every box, without the `plain` one. The evaluation's variants
(`benchmarks/eval/templates/`) are templates files too.
