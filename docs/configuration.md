# Configure

Models, profiles, context, MCP servers, tools, window pictures, and agent sessions.

## Backends and rewrite templates

Claudish supplies the plumbing: the input method, a rewrite template, and the
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

Replace the rewrite template with `--prompt FILE` for any backend:

```json
{"system": "Rewrite, do not reply. Keep names and numbers exactly. Use an em dash.",
 "examples": [["the server is down", "The server is down—currently, and regrettably, unreachable."]]}
```

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
              "prompt": "grand.json"},
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
picture of the window you are typing in. In instruct mode, press **F8** before
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

- Only tools the server marks read-only (`readOnlyHint`) are offered, plus the
  ones you vouch for with `"trust"`. Tools with side effects are never offered;
  they will need a per-call approval in the candidate list (G18).
- Every call appears in "consulted", such as `notes.ci_status(branch="main")`.
- The loop is bounded: at most 4 rounds of calls, and 60 s in all. The result is
  still only a candidate.
- It needs an OpenAI-compatible server whose model calls tools (llama.cpp, whose
  chat templates handle tool calls by default, vLLM, Ollama). On the Spark, Qwen2.5-14B called the right tool and
  drafted from its result ("41 tests have passed… test_upload_retry timed out
  after 30 seconds", 3.1 s), and called none for a haiku. Qwen2.5-1.5B never
  called a tool and wrote around the gap. Claude and agent CLIs come later; an
  agent CLI behind the `command` backend already uses its own tools.

### Agent sessions: an agent at the caret

With `"session_command"` in a profile, a sent instruction (instruct mode, Enter)
runs an agent instead of a single model call. Claudish is the agent's host: its
progress and partial draft show in the input method's status line, its
permission questions become the candidate list, and its final answer is a
candidate like any other. For Claude Code:

```json
{"profiles": {"code": {"backend": "llama",
  "session_command": ["claude", "--print", "--input-format", "stream-json",
    "--output-format", "stream-json", "--verbose", "--include-partial-messages",
    "--permission-prompts", "host"]}}}
```

- *"is my branch clean?"* → `Allow — Bash: git status` / `Deny`: **1** allows that one
  call, **2** denies it (the agent carries on without it). Nothing runs without
  your choice unless your own Claude Code settings already allow it.
- **Esc** at any point stops the agent and keeps your words. Editing the
  instruction stops it too.
- The agent runs with your Claude Code login, settings, and working directory
  (the service's), and its usage counts as yours. A session is limited to five
  minutes and four at a time.
- Status: tested end to end in the Linux desktop container (real IBus and GTK)
  with a scripted agent that speaks Claude Code's stream-json protocol (the
  message shapes come from the Agent SDK's control protocol), plus the PIME smoke
  and the macOS doubles. On Windows, a question shows at your next key press
  (F6). A live run against Claude Code itself is pending.

## Modes

Every request names a mode, and every mode only offers a candidate, which you
accept with Tab or ignore:

| Mode | You type | The candidate |
| --- | --- | --- |
| `rewrite` (default) | a phrase | the phrase, rewritten in house style |
| `continue` | the start of a sentence | your text plus the next few words |
| `instruct` | an instruction, such as "decline politely, propose Thursday" | the text itself, written using the profile's context |

The browser demo has a mode switch. Adapters send `"mode"` in `/suggest`, and
`/health` lists the modes. A profile can replace any mode's template or token
budget, or add a mode of its own:

```json
{"profiles": {"p": {"modes": {"instruct": {"max_tokens": 900},
                               "haiku": {"prompt": "haiku.json", "max_tokens": 60}}}}}
```
