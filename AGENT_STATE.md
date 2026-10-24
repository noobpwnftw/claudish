# Maintainer handoff

Checkpoint 2026-10-25, `main` at `541b8c3`. An interactive session on the Spark; no 24/7 runner.

## Settled

The design is [docs/design/design.md](docs/design/design.md); the request/answer architecture is
[docs/design/architecture.md](docs/design/architecture.md); how it was reached is in
docs/research/. The web is the design: `claudish/web/kit.css`/`kit.js` and the lab
(`design.html`) are the reference, `claudish/composition.py` produces every panel description, and
the natives match the lab state by state. Owner direction: no per-platform special cases; the CJK
input-method reviewers weigh most on keys; get the thing to work before anything else; user-facing
copy says what things do and nothing more.

## Current task

The review-fix pass: six reviewers read every file (2026-10-25). Fixed so far: settings changes keep
sessions and conversations; start.py binds before writing its token and applies settings; the login
service runs the config's profile; Tab never takes a draft over a typed reply; a held exchange never
reuses a revision; Claude's last tool round declares its tools; CJK continue joins without a space;
an insert or handoff survives an empty closing reply; Claude tool turns get 60 s; the gate runs test
files in parallel. Then the wrong-narrative sweep of every user-facing text.

Remaining findings, by area:

- Service and CLI: saving a key with no config file leaves the backend "none"; `service install`
  does not restart a running unit (Linux) and fails when loaded (macOS); doctor sends no key to a
  model server and reads llama's 503 as absent; non-ValueError errors in POST /settings drop the
  connection; `recent --clear`, `rewrite`, `bench` trace back when the service is down; mcp_setup
  prints ✓/✗ without the ASCII fallback; setup always says "paste your Claude key".
- Model: F8 ignored for agent sessions; an unanswered model question holds a session slot forever;
  `mcp import` writes `$VAR`, Claude Code expands only `${VAR}`; the OpenAI-compatible body sends
  llama.cpp-only fields (`cache_prompt`) to hosted APIs; Claude ignores a mode's `max_tokens`;
  effort/fallbacks sent by model-name prefix (Haiku 4.5 400s); one broken MCP server fails every
  instruction; Textbox.search offsets wrong when lowercasing changes length; `recent` misses the
  outcome when every candidate is filtered; Esc does not stop the model-driver loop.
- Composition and web: Tab after a failed instruction rewrites the old instruction; demo paste during
  an exchange wipes it; demo Shift+Esc while composing acts as Esc; demo Shift-tap misses rolled
  and mouse cases; design lab scrolls sideways at 320–375 px; demo wordmark wraps at 320 px; dead
  demo CSS; demo leftovers (`backend`, `hosted` variables).
- Linux and macOS: macOS `setMarkedText_("")` with nothing marked can delete a selection; IBus
  `finish()` ignores a sent instruction (commits it and drops the exchange); macOS deactivation
  closes the worker, so a held exchange's work is lost; IBus dead keys break in compose; a reply
  being typed is committed on focus change; Linux install.py symlink breaks on a moved checkout;
  panel clamped to the wrong monitor (macOS, GNOME); macOS toast timers not cancelled; Shift+Enter
  on a sent instruction does not cancel the request; NSAttributedString ranges in code points;
  package.py accepts an empty hostArchitectures; build.py `--install` text stale.
- Windows: the taskbar indicator click passes a null edit session into the toast (crash risk); on
  ARM64 the x64 forwarder target is the stock PIME's DLL; a missing x64/arm64 folder in the tree
  ships no DLL silently; continue Backspace counted twice; the suggestion is not hidden after
  Enter, arrows, Backspace, Delete; panel and suggestion stay after focus leaves; the suggestion
  window is owned by the first window; other PIME backends' input methods get registered; make_source.sh
  relative output path; the input source is added for the elevated account; timers map shared
  across threads; build-pime.ps1 hard-codes the VM share; update does not stop PIME's backend; dead
  `mark` code in both patches.
- Tests and docs: three test files call `unittest.main()` before later classes (direct runs skip
  them); the tmux test depends on timing; check.py leaves the settings-page service on a timeout.

## Release 0.1.0

Not released. One blocker: a rewrite through Claude with a valid Anthropic API key, which only the
owner can run (docs/release.md on branch `agent/release-0.1.0`, which also holds the
download-first README and site and the release notes; it needs a rebase onto main).

## Checks (owner, 2026-10-24)

The gate is `python scripts/check.py`, every step under 5 s (unit tests run one process per file:
about 1.5 s, 2.7 s with the `[claude,mcp]` extras). Real typing is checked by hand. Remote CI is
paused by the owner. Merge rule: `check.py` passes on the merged result; main is fast-forward only.

## Running (owned)

- llama-server with Gemma 4 E4B on the Spark, bound to the network for the Mac and Windows VMs'
  "Another model API" (`http://10.0.0.249:18790`), pid 689074 in the scratchpad's gemma-lan.pid.
  Stop it when the hand tests are done.

## Environment and owned resources

- Mac VM: `ssh -i ~/.ssh/claudish_mac_vm claudish@10.0.0.251`, repo ~/claudish (sync by tar over
  ssh). Build `.tools/macos-build-venv/bin/python platforms/macos/build.py`, then
  `platforms/macos/package.py` and install the .pkg; auto-login, so a restart is the logout. Never
  click the owner's consent dialogs; warn before a rebuild that needs an Allow or a relogin.
- Windows 11 ARM64 VM (dockur container): Claudish's patched PIME is built there with VS Build Tools
  into C:\PIME-build; `platforms/windows/package.py` builds cd_AI-setup.exe over it. Job runner and
  helpers are in the session scratchpad's win/ folder.
- Models in `models/` (untracked): Qwen2.5 0.5B and SmolLM2 135M, Gemma 4 E2B/E4B/12B/26B-A4B (QAT
  Q4_0; the 26B is the judge), Qwen3-30B-A3B (tool and agent checks), Qwen2.5-VL-3B with its mmproj.
  Extras venv `.tools/claude-venv`; browser venv `.tools/browser-venv`; CUDA llama.cpp in
  `.tools/build`.
- claudish.io: site/ plus the static demo at /demo/, deployed by .github/workflows/pages.yml on
  every push to main.
- Waiting on the owner: deleting old remote branches; publishing the release.
