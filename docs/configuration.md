# Configure

Models, profiles, context, MCP servers, tools, window pictures, and agent sessions.

## Backends

Claudish supplies the plumbing: the input method, its templates, and the
service between them. How well a model follows the
template depends on that model. `benchmarks/evaluate.py` measures any backend
on the same cases.

Use any OpenAI-compatible server and any model, such as llama.cpp, vLLM, Ollama,
LM Studio, or a hosted endpoint:

```sh
claudish serve --backend openai --model-url http://127.0.0.1:11434 --model your-model
# A remote endpoint, with a key read from an environment variable that you name:
claudish serve --backend openai --model-url https://api.example.com \
    --model some-model --api-key-env EXAMPLE_API_KEY --timeout 10
```

Or use Claude through the official SDK, which every installer includes (in a source checkout:
`.venv/bin/python -m pip install -e ".[claude]"`). The key comes from cd_AI's settings,
`ANTHROPIC_API_KEY`, or `ant auth login`.

```sh
claudish serve --backend claude                     # claude-opus-5-5
claudish serve --backend claude --claude-model claude-haiku-5-5
```

`claudish` is cd_AI's command line ([where it is on each OS](install.md#the-claudish-command)).
These run a service in the foreground; the login service (`claudish service install`) runs the
config's profile instead.

For a deterministic demo without a model, use `claudish serve --backend rules`. That mode performs simple word substitutions and identifies
itself as `rules` in API responses. It does not perform neural rewriting.

The Claude backend runs one request at a time, at low effort, with server-side refusal
fallbacks on the models that offer them. No model ships: the starter profile is Claude, and
`--profile local` is the local one.

Change what the model is told with a templates file, for any backend (see
[Templates](#templates)): `claudish serve --templates FILE`, or a profile's
`"templates"`.

### Apps: bindings

The input method knows which app has focus. On Linux, IBus reports the program
(`gtk3-im:thunderbird` arrives as `thunderbird`). On macOS it is the bundle identifier
(`com.apple.Terminal`); on Windows, the program file (`notepad.exe`). A binding
matches apps by a case-insensitive glob and sets, for them, which profile answers
(its backend, tone, tools and helper) and context the model gets there every time:

```json
{"profile": "claude", "profiles": {
  "claude": {"backend": "claude", "bindings": [
    {"app": "thunderbird*", "context": [{"type": "file", "path": "~/notes/email-style.md"}]},
    {"app": "slack*", "profile": "proofread", "context": [{"type": "file", "path": "~/notes/team-glossary.md"}]},
    {"app": "gnome-terminal-server", "profile": "agent"}]},
  "proofread": {"backend": "claude", "tone": "proofread"},
  "agent": {"backend": "claude", "helper": ["claude", "{prompt}"]}}}
```

A binding holds what is true of an app every time: who answers there, a style
guide, a glossary. What changes from one request to the next comes with the
request: the text around the caret, a terminal's last lines, the window's
picture (F8), and the [tools](#tools-instructions-that-look-things-up) the model calls for
what you asked ("summarize PR 1234 for the standup" reads that PR). Elsewhere, the service's own profile
answers with its own context. Every response lists what was `consulted`.

A mode can name the profile that answers it, too: continue runs at every pause
and wants a small, fast model; an instruction is sent on purpose and can wait
for a strong one. Continue suggests only with a local model or where a profile
routes it like this; otherwise continue types as is.

```json
{"profiles": {"claude": {"backend": "claude", "modes": {"continue": {"profile": "tiny"}}},
              "tiny": {"backend": "llama", "model_url": "http://127.0.0.1:18766"}}}
```

The app's binding chooses first, then that profile's choice for the mode. The
service's own profile (`claudish serve --profile`, or the file's `"profile"`)
holds the bindings; other profiles are loaded when they are first needed.

### An agent CLI as the backend

With `"backend": "command"`, Claudish sends the mode's instructions, the profile's context, and your text on
stdin; the command's output becomes the candidate, which you accept with Tab. The settings page's
**Claude Code** choice writes this profile, with the full path to `claude` (a login service may
not have your shell's PATH), for a Claude subscription:

```json
{"profiles": {"claude-code": {"backend": "command", "timeout": 30,
                              "command": ["/home/me/.local/bin/claude", "-p", "--model", "haiku", "--output-format", "text"]}}}
```

The **Codex** choice writes the same kind of profile for a ChatGPT subscription; `codex exec` reads
the text on `-` (stdin) and works read-only in cd_AI's config folder:

```json
{"profiles": {"codex": {"backend": "command", "timeout": 60,
                        "command": ["/home/me/.local/bin/codex", "exec", "--skip-git-repo-check", "--ephemeral",
                                    "-s", "read-only", "-C", "/home/me/.config/claudish", "-"]}}}
```

A longer-running agent, for instructions:

```json
{"profiles": {"agent": {"backend": "command", "timeout": 120,
                        "command": ["claude", "-p", "--output-format", "text"]}}}
```

Any CLI that reads a prompt on stdin works: `claude -p`, `ollama run MODEL`,
`llm`, or a script. Tool permissions are the CLI's
own; for example, Claude Code's `--allowedTools` in the command list. Agents are
slow, so the profile's `timeout` applies (`/health` reports it).

Measured on a DGX Spark (GB10) with Claude Code 2.1.306: an instruct request ("thank
Priya for fixing the flaky CI job, it saved the release") returned a finished,
em-dashed thank-you note in 4.5 s.

### Profiles

Instead of passing flags, declare your backends once in
`~/.config/claudish/config.json` (or `$XDG_CONFIG_HOME/claudish/config.json`, or
pass `--config FILE`):

```json
{"profile": "claude",
 "profiles": {
   "claude": {"backend": "claude", "claude_model": "claude-opus-5-5"},
   "ollama": {"backend": "openai", "model_url": "http://127.0.0.1:11434", "model": "gemma3:4b"},
   "remote": {"backend": "openai", "model_url": "https://api.example.com", "model": "some-model",
              "api_key_env": "EXAMPLE_API_KEY", "timeout": 10},
   "local":  {"backend": "llama"}
 }}
```

`claudish serve` uses the file's `"profile"`. `--profile claude`
picks another, and any flag overrides the profile's value. A template path in a
profile is relative to the config file. To take a key from the environment, name
its variable with `api_key_env`. Unknown keys and wrong types are rejected at startup. `/health` reports the active profile.

### Window pictures

For apps that publish nothing Claudish can read, an instruction can carry a
picture of the window you are typing in. In compose, press **F8** before
Enter: the hint shows "instruct + window picture", and the service captures the
focused window once, sends it with that one instruction, and lists it in
"consulted". F8 applies to that one instruction.

- **Capture:** Windows uses PrintWindow (built in). Linux X11 needs `xprop` and
  ImageMagick (`sudo apt install x11-utils imagemagick`). Elsewhere, set the profile's
  `"look_command"` to a program that writes a PNG of the focused window to stdout: on macOS a
  `screencapture` wrapper, on wlroots compositors (Sway, Hyprland) a `grim` wrapper. GNOME on
  Wayland lets no program capture a window without asking, so F8 has no picture there.
- **Backends:** `claude` and any OpenAI-compatible server with a vision model.
  For llama.cpp, start a vision model with its projector, for example
  [Qwen2.5-VL-3B](https://huggingface.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF):
  `llama-server -m Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf --mmproj
  mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf -c 8192`. The `command` backend refuses.

Verified with a real capture in both places. On Windows 11 ARM64, a Notepad
invoice was captured with PrintWindow and sent to Qwen2.5-VL-3B (Q4_K_M) on a
DGX Spark's GPU; "what is the amount due here?" returned "The amount due is 1,250.00
EUR." in 0.18 s.

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

Results are cached for `ttl` seconds (default 30). A failing or slow provider (`timeout`,
default 5 s) is skipped. Context goes in the user turn, ahead of your text. Adapters may also
send the text around the caret as `before`/`after` in `/suggest`.

MCP servers can supply context too. They need the MCP SDK: after the one-line install on Linux, `~/.local/share/claudish/.venv/bin/python -m pip install -e "$HOME/.local/share/claudish[mcp]"`; in a checkout, `.venv/bin/python -m pip install -e ".[mcp]"`. Claudish
starts the configured stdio server, calls one tool or reads one resource, and
caches the text:

```json
{"type": "mcp", "name": "style guide", "command": ["github-mcp-server", "stdio"],
 "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "$GITHUB_TOKEN"},
 "tool": "get_file_contents", "arguments": {"owner": "me", "repo": "app", "path": "docs/STYLE.md"},
 "ttl": 3600, "timeout": 15}
```

`"$NAME"` values in `env` are read from your environment. Use `"resource": "uri"` instead of `"tool"` to read a resource.

Already using MCP servers with Claude? Bring them along:

```sh
claudish mcp import            # from Claude Desktop, Claude Code (~/.claude.json), and ./.mcp.json
claudish mcp list              # connect to each server; show its tools and resources
claudish context test --app thunderbird --show   # what a binding would read in that app
```

Imported servers land under `"mcp_servers"` in your config and are used by name:
`{"type": "mcp", "server": "github", "tool": "...", "arguments": {...}}`. Every `env` and
header value becomes a `$NAME` reference, and `import` lists the variables to set.

Apps that publish MCP on a local socket are read with `url` instead of
`command`: streamable HTTP by default, or `"transport": "sse"`. Headers may use
`"$NAME"` values from your environment:

```json
{"type": "mcp", "name": "editor", "url": "http://127.0.0.1:3920/mcp",
 "headers": {"Authorization": "Bearer $EDITOR_MCP_TOKEN"}, "tool": "get_selection"}
```

### Tools: instructions that look things up

Context is read before the model starts. Tools go further: an instruction may
*call* MCP tools while it works, then draft from what they returned, for example
"tell the team how CI looks on main". Define the servers under `mcp_servers` (or bring them
with `claudish mcp import`) and name them in a profile's `tools`:

```json
{"mcp_servers": {"github": {"command": "github-mcp-server", "args": ["stdio"],
                            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "$GITHUB_TOKEN"}}},
 "profiles": {"claude": {"backend": "claude",
                         "tools": [{"server": "github", "trust": ["get_pull_request_diff"], "deny": ["merge_pull_request"]}]}}}
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
  its text box goes away or after 30 idle minutes.
- Every call appears in "consulted", such as `notes.ci_status(branch="main")`.
- The loop is bounded: at most 4 rounds of calls, and 60 s in all.
- It needs a model that calls tools: Claude, or an OpenAI-compatible server whose model does
  (llama.cpp, whose chat templates handle tool calls by default, vLLM, Ollama). Gemma 4 E4B, the
  local model, called `ci_status` for "tell the team how CI looks on main" and drafted from its
  result. An agent CLI (`session_command`) uses its own tools.

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

- *"is my branch clean?"* → `Deny` / `Allow — Bash: git status`: ↓ to a choice and Enter
  answers (Allow is a deliberate ↓↓ Enter; Deny lets the agent carry on without it), or type a reply and
  press Enter: it denies the call with your words as the reason ("use git diff
  instead"), so the agent can adjust. Claude Code's own settings may allow a call
  without asking.
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
- **The agent gets the profile's tools.** The servers named in the profile's `tools` are
  passed to it (`--mcp-config`), under the same policy as the model:
  `deny` tools are never offered (`--disallowedTools`), `trust` tools run
  without asking, the rest ask. The profile's `context` and the app's bindings go
  with each instruction, as they do for the model.
- **The agent sees your text box.** The text around the caret goes with each
  instruction, and with the `[mcp]` extra installed, Claudish gives the agent a
  `textbox` MCP server (read, search) for the rest, so "fix the second paragraph"
  works in a long document. Its reads run without asking. Without an agent, the model driver has the same two tools
  whenever the text box is longer than what it is sent.
- The agent runs with your Claude Code login, settings, and working directory
  (the service's), and its usage counts against that login. A session is limited to five
  minutes and four at a time.
- Status: tested with a scripted agent that speaks Claude Code's stream-json protocol (the
  message shapes come from the Agent SDK's control protocol), the PIME smoke and the macOS
  doubles, and live against Claude Code (2.1.308). On Windows (Claudish's
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
screen). Not offered when the program is not installed or
the command skips the helper's own permission prompts. Needs a backend with
tool calls (llama.cpp, any OpenAI-compatible server, or Claude).

With `{session}` in Claude Code's command, Claudish starts it on a session id it
chose and keeps that in the text box's conversation, so a later "is it done?" in
the same box can read the helper's latest messages from its own transcript:

```json
{"profiles": {"local": {"helper": ["claude", "--session-id", "{session}", "{prompt}"]}}}
```

Codex is followed the same way, through the session that mentions the handoff
note; any other helper can be followed when a tmux launcher names its window
(`["tmux", "new-window", "-n", "{name}", "{command}"]`): Claudish reads the
window's last lines.

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

cd_AI's default tone is corporate slop: "ok" becomes a paragraph about shared vision and
synergies. A profile can pick another tone:

```json
{"profiles": {"work": {"backend": "claude", "tone": "critic"}}}
```

| Tone | Sounds like | "nah" becomes, roughly |
| --- | --- | --- |
| `corporate` (the default) | LinkedIn and consultant slop | "…may not align with our broader strategic objectives—at least not at this stage of our journey." |
| `salesman` | a breathless closer | "…believe me, it hurts, because I love a deal—but this offer just isn't right for us today!" |
| `critic` | haughty, world-weary, faintly disappointed | "No. I have considered it, briefly and against my better judgement, and the answer remains no." |
| `bard` | an Elizabethan bard at the playhouse | "Nay, good friend, it cannot be; my answer standeth firm: no." |
| `proofread` | you, with the typos fixed | "nah" |

`proofread` corrects spelling, typos, grammar and capitals; continue and instruct are plain
then. Any other few words work too ("warm and friendly", "plain and concise"); they
replace the tone in each template, without examples. `claudish setup --tone critic` sets it for
you. The tones are templates like the rest ([Templates](#templates)): change one, or add one
under `"tones"` in your templates file. A mode's own `"system"` in the profile's templates wins
over the tone. Instructions typed in a terminal always get a command line.

## Modes

Every request names a mode:

| Mode | You type | The candidate |
| --- | --- | --- |
| `rewrite` (default) | a phrase | the phrase, rewritten in house style |
| `continue` | the start of a sentence | your text plus the next few words |
| `instruct` | an instruction, such as "decline politely, propose Thursday" | the text itself, written using the profile's context |

At the caret, compose's Tab asks for `rewrite`, its Enter sends `instruct`, and continue mode
(a Shift tap) asks for `continue`. Adapters send `"mode"` in `/suggest`, and
`/health` lists the modes. A profile's templates can change any mode, or add one
of its own; its `"modes"` says only which profile answers a mode (above).

## Templates

The templates are in
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
as written in every box, without the `plain` one. A tone of your own goes under
`"tones"`, and a profile picks it by name (`"tone": "pirate"`):

```json
{"tones": {"named": {"pirate": {"about": "Arr.", "modes": {
  "rewrite": {"system": "Rewrite the user's text as a pirate would say it. Keep the meaning, names and numbers.",
              "examples": [["ok", "Aye, aye—'tis agreed, matey!"]]}}}}}}
```

`claudish init` writes such a file beside the config, `templates.json`, with a tone to start
from, and points the profiles at it. `claudish templates` prints what a profile ends up with: the
shipped templates, your file over them, and the tone, as the model is told it. The evaluation's
variants (`benchmarks/eval/templates/`) are templates files too.
