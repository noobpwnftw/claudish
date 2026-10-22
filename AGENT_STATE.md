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
- claudish.io: bought by the owner; DNS not resolving yet (no NS on 2026-10-23). When it does:
  set the Pages custom domain, wait for HTTPS, switch README and repo homepage. Not before:
  a custom domain redirects the github.io home page.
- Next: G18 (agent sessions at the caret; approval of side-effecting tools as
  candidate choices); then G21 (browser model data).
- Windows: 9/9 typing scenarios pass on Windows 11 ARM64 (VM `claudish-windows`,
  `~/vm/claudish-windows`, account Docker/admin, a local throwaway). The VM has PIME
  master build 656 plus the x86 VC++ runtime. Loop: `vm.sh sync`, `vm.sh run
  jobs/deploy.ps1 40`, `vm.sh run jobs/typing.ps1 90`. `vmscreen.sh OUT.png
  ['sendkey …']` gives a screenshot in about 1 s; `vmkeys.py` types exact text.
- Home page: https://noobpwnftw.github.io/claudish/ is the static demo (the model runs in the
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
