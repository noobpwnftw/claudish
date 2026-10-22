# Maintainer handoff

Checkpoint 2026-10-22 (an interactive session on the Spark; no 24/7 runner).

- `main` (`a1f567a`) adds since the last checkpoint:
  - G01 Linux: real IBus/GTK desktop tests (`check.py --desktop`) and the fixed
    installer (environment.d search path, `--system`, `--uninstall`, layout
    `default`).
  - G15: rewrite/continue/instruct modes in the service, the browser demo, and
    F7 in all three adapters.
  - G12: a local 14B meaning judge, with 91.5% same-vs-not agreement on hand
    labels.
  - G16: `claudish fix` (bash 3 and Windows fixes included).
  - G05: CONTRIBUTING.md.

  The full gate `check.py --model --desktop` passes.
- Windows: 9/9 typing scenarios pass on Windows 11 ARM64 (VM `claudish-windows`,
  `~/vm/claudish-windows`, account Docker/admin, a local throwaway). The VM has PIME
  master build 656 plus the x86 VC++ runtime. Loop: `vm.sh sync`, `vm.sh run
  jobs/deploy.ps1 40`, `vm.sh run jobs/typing.ps1 90`. `vmscreen.sh OUT.png
  ['sendkey …']` gives a screenshot in about 1 s; `vmkeys.py` types exact text.
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
