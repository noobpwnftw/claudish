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
- Text box retrieval (a7be0e9): textbox.read/search for the model driver (local tools, no
  MCP SDK needed) and `claudish textbox-mcp` for agents (--mcp-config file, token-gated).
  CI 39867515381 (5 jobs) and the gate pass. Live check with
  models/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf (owner: use a better local model for
  framework checks; llama-server --jinja -ngl 99): retrieval, follow-ups, MCP read/write OK.
  Script: the session scratchpad's live_instruct.py (rewrite it if lost: long text box,
  three follow-ups, a short box, two MCP turns).
- Fixed flake (20761c1): the desktop test now waits for the grey suggestion (preedit).
- Live Claude Code checked (7fbdd4f; owner allows live runs on their quota, use haiku):
  per-conversation process, textbox MCP reads, Allow/Deny questions, worded denial, Esc.
  Fixed: --permission-prompt-tool stdio is required for host prompts.
- macOS (d29b27f): surrounding text via IMK, grey suggestion, instructions carry the text
  box; doubles and CI only. The owner's desktop is a Mac (VS Code remote to the Spark):
  the first real-Mac run is theirs (python3 platforms/macos/build.py --install).
- Mac VM (owner's UTM, macOS 26.6.2): ssh -i ~/.ssh/claudish_mac_vm claudish@10.0.0.251,
  passwordless sudo, Python 3.12.10 from python.org, repo in ~/claudish, service on the rules
  backend (nohup python3 -m claudish serve --backend rules). Rig: tests/desktop/macos/driver.py,
  9/9 twice (209e936). Rebuilding cd_AI makes macOS ask the owner to Allow again: warn
  them first; the rig waits for the click (fresh processes: TIS caches per process), then
  closes System Settings. Owner saw the candidate panel with 3 readings after the show_ fix.
- Risk (macOS): if cd_AI crashes, macOS does not restart it until login, and typing with it
  selected does nothing. Two crashes fixed today (stringFromRange NULL, per-controller panel). No Screen Recording over SSH yet (screencapture fails). CLAUDISH_TRACE is set in
  the VM's launchd for cd_AI traces.
- Still open: Claude API tool loop (needs credentials), selection from the adapters, VS Code +
  Claude Code chat box on the Mac VM.
- G34 (functionality before visuals), b0978b2: typed agent replies; one text box description
  for every mode (app, field kind, text around the caret); quiet in URL/email/number fields;
  agents get the profile's MCP servers, policy, context (checked live); rewrite on Tab and of
  a selection (macOS, demo; GTK reports no selection; Edge ends compositions over text);
  native mode indicators (GNOME verified; Windows icon seen; macOS input modes built, VM run
  pending); Claudish's patched PIME in platforms/windows/pime (timer redraw, text around the
  caret, selection, input scopes, document id; built in the VM with VS 2022 Build Tools,
  jobs/buildtools.ps1 + build-pime.ps1; Notepad 15/15, Edge 14/14 + 1 known).
- Waiting on the owner: Mac VM run of the input modes (rebuild = one Allow click); whether F7
  should be configurable; Claude API tool loop needs a key.
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
