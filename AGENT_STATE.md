# Maintainer handoff

Checkpoint 2026-10-24, `main` at `626fe8d`: the visual pass merged (every native's lab preview
reviewed against the lab). An interactive session on the Spark; no 24/7 runner.

## Settled

The design is [docs/design/design.md](docs/design/design.md); the request/answer architecture is
[docs/design/architecture.md](docs/design/architecture.md); how it was reached is in
docs/research/. The web is the design: `claudish/web/kit.css`/`kit.js` and the lab
(`design.html`) are the reference, `claudish/composition.py` produces every panel description, and
the natives match the lab state by state. Owner direction: think at the architecture level, no
per-platform duct tape; the CJK input-method reviewers weigh most on keys.

## Current task

G45, the visual pass: every presentation (lab, demo, homepage, docs, the three natives) brought to
the settled design and checked against the lab by reviewers with gallery screenshots, then merged.

## Verified (latest)

- Gate `scripts/check.py --model` 10/10 (`--desktop` 13/13 just before) and CI 5/5 on `626fe8d`.
- Lab previews (`gallery.sh OUT preview`) reviewed state by state against the lab: Windows 20/20
  (the legend's em dash fixed: MSVC reads source as cp1252, so non-ASCII literals are `\u` escapes),
  macOS 20/20, GNOME 8/8. Demo footer stays on one line at 390/768/1280.

## Open, waiting, or parked

- Owner decisions: the summon key default (G47). Dropped: keeping the panel inside the app's window.
- Parked: the Claude API tool loop against the live API (needs a key); G30 (needs releases); G21
  (a trained model); an upstream PIME proposal (a public post: owner's OK).
- Known: Linux GTK reports no selection (Qt does); macOS Terminal keeps Tab from continue's
  suggestion (G50).

## Environment and owned resources

- Mac VM: `ssh -i ~/.ssh/claudish_mac_vm claudish@10.0.0.251`, repo ~/claudish (sync by tar over
  ssh; `git stash` holds older VM-local edits). Build `.tools/macos-build-venv/bin/python
  platforms/macos/build.py`, install in place `tests/desktop/macos/driver.py --reinstall`. The
  service must run on the venv's Python (`.tools/macos-build-venv/bin/python -m claudish serve
  --backend rules`): system Python has no AppKit, so it cannot read a terminal's screen. Never
  click the owner's consent dialogs or write AppleEnabledInputSources; warn before a rebuild that
  needs an Allow or a relogin. Gallery: `tests/desktop/macos/gallery.sh` with vncdotool.
- Windows VM `claudish-windows` (container; `tests/desktop/windows/vm.sh start|stop`): Claudish's
  patched PIME, built there with VS Build Tools. Loop: `vm.sh sync` (the last commit), `vm.sh pime`
  and `vm.sh run jobs/build-pime.ps1 900` when the patches change, `vm.sh run jobs/deploy.ps1
  300`, `vm.sh run jobs/typing.ps1 400`; `gallery.sh OUT`; `vmscreen.sh OUT.png`.
- Models in `models/` (untracked): Qwen 0.5B/1.5B/14B, Qwen3-30B-A3B, Qwen2.5-VL-3B. Extras venv
  `.tools/claude-venv`; browser venv `.tools/browser-venv`.
- claudish.io: site/ plus the static demo at /demo/, deployed by .github/workflows/pages.yml on
  every push to main.
- Merge rule: clean `check.py --model` on the merged result, a `ci/*` run for Windows/macOS
  adapters or packaging (check the jobs on the actual head SHA); main is fast-forward only.
