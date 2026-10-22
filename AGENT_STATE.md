# Maintainer handoff

Checkpoint 2026-10-23 (an interactive session on the Spark; no 24/7 runner).

- `main` adds the onboarding priority (owner, 2026-10-23: "the IME and MCP side
  of things for a better on-boarding experience"):
  - G22 `claudish doctor`, G23 `claudish service`, G24 `claudish mcp
    import|list` and `claudish context test`.
  - G25 `claudish setup`, a wizard over all of them, plus
    `scripts/download_llama.py` (pinned b11822, digest-verified). It was verified
    for real in `tests/desktop/linux-systemd`: a fresh copy, `setup --yes`, and
    the login service answers from the downloaded CPU llama-server.
  - `start.py` now uses the local profile's context and bindings.
  - URL openers are built once: this fixed an exit-time segfault (the IBus smoke
    failed 5 in 60, now 0 in 60) and halved the gate's median latency (63 to 33 ms).

  The full gate `check.py --model --desktop` and CI run 39828326815 (all 5 jobs)
  pass on `265f0ec`.
- G25 is verified on Windows ARM64 too (VM job `setup-wizard.ps1`). That run
  found and fixed an orphaned llama-server after `service uninstall` (job object)
  and added a curl.exe fallback for certificate failures on Windows.
- G26 done: F8 window pictures (Windows PrintWindow, X11 ImageMagick, look_command);
  verified with Qwen2.5-VL-3B (models/, with its mmproj) on the Spark.
- G27 first slice done: instruct offers up to 3 readings, 1-9 pick (all adapters, demo).
- G17 second step done: profile "tools" (read-only MCP tools in a bounded loop, OpenAI-compatible).
- claudish.io (owner's domain, name.com DNS): the Pages custom domain since 2026-10-23,
  HTTPS enforced, www and the old github.io URL redirect; verified isolated in Chromium.
- G18 first slice: agent sessions (Claude Code stream-json host; questions as choices).
  Scripted-agent tested; a live Claude Code run waits for the owner's OK (their quota).
- G17/G18 conversations (a481e05): one conversation per text box; the model driver
  keeps turns and asks for write tools; the agent driver keeps one agent process per
  conversation (--session-id, Esc interrupts, --resume after exit, exits with the
  conversation). Gate --model --desktop and CI 39865449511 (5 jobs) pass.
  Next: textbox retrieval tools (textbox.read/search/selection) and Claudish as an
  MCP server for the conversation's agent.
- The demo's continue sample must differ from the continue example's input (f5f7ac3):
  otherwise parroted() drops the answer and the demo shows nothing.
- Home page: site/ at claudish.io, the demo at /demo/, an agent install prompt; releases
  are a placeholder (owner: no rush; CHANGELOG.md drafts 0.1.0).
- G28: continue types into the app, the suggestion waits after the caret; F7 always
  switches modes. Linux 24/24, Windows Notepad 11/11 and Edge 10/10.
- G29: GNOME Shell on Wayland in the desktop gate (tests/desktop/linux-gnome, 10/10).
- Owner focus (2026-10-23): make the en_US -> cd_AI switch feel natural, without regressions.
  Done: sessions start in continue (keys straight in, literally); F7 is continue, instruct,
  rewrite. Linux X11 25/25, GNOME 10/10, Windows Notepad 12/12, Edge 11/11.
- Owner: models are placeholders until G21 (a trained model); polish the framework, not the models.
- Next: framework polish (demo, switch, onboarding); G30 auto-update needs releases.
- Windows: 9/9 typing scenarios pass on Windows 11 ARM64 (VM `claudish-windows`,
  `~/vm/claudish-windows`, account Docker/admin, a local throwaway). The VM has PIME
  master build 656 plus the x86 VC++ runtime. Loop: `vm.sh sync`, `vm.sh run
  jobs/deploy.ps1 40`, `vm.sh run jobs/typing.ps1 90`. `vmscreen.sh OUT.png
  ['sendkey …']` gives a screenshot in about 1 s; `vmkeys.py` types exact text.
- Home page: https://claudish.io is the static demo (the model runs in the
  visitor's browser via wllama; coi-sw.js supplies isolation; about 1.4 s per rewrite live). It
  is deployed by .github/workflows/pages.yml on every push to main, and it is the repository
  homepage (owner-approved). Next: G21, a purpose-trained ~150 MB browser model, starting with
  training data. The Edge shortcut issue (G01) is tabled by the owner.
- Owner direction: Claudish is a configurable entry point for AI at the caret
  (models, then context, then modes, then agentic instruct, G17). Model quality
  belongs to the model. The name and the em dashes stay. Use the Spark
  (containers, KVM VMs, local models) instead of GitHub CI; run `ci/*` branches
  for Windows and macOS coverage.
- Evidence limits: macOS is covered only by the Cocoa doubles and the CI bundle
  build. The Claude backend has never been called live (no credentials). The zsh
  hook is unrun. Wayland/GNOME and Qt are untested.
- Environment: `gh` is authorized and backs git. The extras venv
  `.tools/claude-venv` has anthropic 2.1.0 and mcp 2.3.0. Models in `models/`
  (untracked): Qwen 0.5B, 1.5B, and 14B (the judge), and SmolLM2.
- Owned background work: the `claudish-windows` VM container (8 GB RAM, 6 cores;
  stop with `tests/desktop/windows/vm.sh stop`).
  Ports 18765/18766 are free.
